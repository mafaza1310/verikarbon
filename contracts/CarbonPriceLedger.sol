// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";
import "./CarbonPassport.sol";

/**
 * @title CarbonPriceLedger
 * @notice Records carbon prices actually paid in the country of origin (e.g. under the
 *         Turkish ETS) and lets EU declarants deduct them from CBAM obligations exactly once.
 *
 *         The problem: CBAM lets importers deduct a carbon price already paid where the good
 *         was produced. Without a shared ledger, the same domestic payment could be
 *         presented by several importers, or several times, across separate declarations.
 *
 *         Enforced invariants:
 *          - sum of deductions claimed against a payment  <= emissions that payment covered
 *          - deductions by a declarant on a passport      <= embedded emissions it declared
 *          - payment and passport must belong to the same installation and the same year
 *
 *         Units: emissions in kgCO2e, money in euro cents.
 */
contract CarbonPriceLedger is AccessControl {
    bytes32 public constant REGISTRY_ROLE = keccak256("REGISTRY_ROLE"); // national registry / regulator

    struct Payment {
        address operator;
        uint64  period;
        uint256 coveredKgCO2e;   // emissions covered by the payment (e.g. allowances surrendered)
        uint256 amountEurCents;  // effective carbon price paid, converted to EUR
        uint256 claimedKgCO2e;   // already deducted by declarants
        bytes32 evidenceHash;    // hash of registry surrender record
    }

    CarbonPassport public immutable passports;
    uint256 public nextPaymentId = 1;
    mapping(uint256 => Payment) public payments;
    /// passportId => declarant => kgCO2e already deducted
    mapping(uint256 => mapping(address => uint256)) public deductedBy;

    event PaymentRecorded(uint256 indexed paymentId, address indexed operator, uint64 period, uint256 coveredKgCO2e, uint256 amountEurCents);
    event DeductionClaimed(uint256 indexed paymentId, uint256 indexed passportId, address indexed declarant, uint256 kgCO2e, uint256 valueEurCents);

    error UnknownPayment(uint256 paymentId);
    error Mismatch();
    error InvalidInput();
    error DoubleDeduction(uint256 requestedKg, uint256 remainingKg);

    constructor(address admin, CarbonPassport passports_) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        passports = passports_;
    }

    function recordPayment(
        address operator,
        uint64 period,
        uint256 coveredKgCO2e,
        uint256 amountEurCents,
        bytes32 evidenceHash
    ) external onlyRole(REGISTRY_ROLE) returns (uint256 id) {
        if (operator == address(0) || coveredKgCO2e == 0 || evidenceHash == bytes32(0)) revert InvalidInput();
        id = nextPaymentId++;
        payments[id] = Payment(operator, period, coveredKgCO2e, amountEurCents, 0, evidenceHash);
        emit PaymentRecorded(id, operator, period, coveredKgCO2e, amountEurCents);
    }

    /// @notice Deduct a domestic carbon price from a CBAM obligation, once and only once.
    /// @return valueEurCents the deductible carbon price for the claimed emissions
    function claimDeduction(uint256 paymentId, uint256 passportId, uint256 kgCO2e)
        external
        returns (uint256 valueEurCents)
    {
        if (!passports.hasRole(passports.DECLARANT_ROLE(), msg.sender)) {
            revert AccessControlUnauthorizedAccount(msg.sender, passports.DECLARANT_ROLE());
        }
        if (kgCO2e == 0) revert InvalidInput();
        Payment storage pay = payments[paymentId];
        if (pay.operator == address(0)) revert UnknownPayment(paymentId);

        CarbonPassport.Passport memory p = passports.getPassport(passportId);
        if (p.operator != pay.operator || p.period != pay.period) revert Mismatch();

        // 1. the payment itself cannot be over-claimed (across all declarants)
        uint256 paymentRemaining = pay.coveredKgCO2e - pay.claimedKgCO2e;
        if (kgCO2e > paymentRemaining) revert DoubleDeduction(kgCO2e, paymentRemaining);

        // 2. a declarant cannot deduct more than the embedded emissions it actually declared
        uint256 declared = passports.declaredEmbeddedBy(passportId, msg.sender);
        uint256 passportRemaining = declared - deductedBy[passportId][msg.sender];
        if (kgCO2e > passportRemaining) revert DoubleDeduction(kgCO2e, passportRemaining);

        pay.claimedKgCO2e += kgCO2e;
        deductedBy[passportId][msg.sender] += kgCO2e;
        valueEurCents = (pay.amountEurCents * kgCO2e) / pay.coveredKgCO2e;
        emit DeductionClaimed(paymentId, passportId, msg.sender, kgCO2e, valueEurCents);
    }

    function remainingKgCO2e(uint256 paymentId) external view returns (uint256) {
        Payment storage pay = payments[paymentId];
        if (pay.operator == address(0)) revert UnknownPayment(paymentId);
        return pay.coveredKgCO2e - pay.claimedKgCO2e;
    }
}
