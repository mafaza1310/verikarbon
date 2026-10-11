// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/access/AccessControl.sol";

/**
 * @title CarbonPassport
 * @notice Non-transferable "embedded emissions passport" for one production batch of a
 *         CBAM good (e.g. Turkish rebar shipped to the EU).
 *
 *         Key guarantees (what a shared database run by one party cannot give):
 *          1. Quantity conservation: the tonnes of a batch can be either consumed as a
 *             precursor by a downstream batch OR declared into the EU, never more than
 *             were produced -> precursor emissions cannot be double counted or "lost".
 *          2. Separation of duties: the operator who creates a passport can never be the
 *             verifier who approves it.
 *          3. Only hashes are stored on-chain (evidence Merkle root, post-quantum hybrid
 *             attestation hash) -> commercially sensitive plant data stays private.
 *
 *         Units: mass in kg, emissions in kgCO2e.
 */
contract CarbonPassport is AccessControl {
    bytes32 public constant OPERATOR_ROLE  = keccak256("OPERATOR_ROLE");  // producing installation
    bytes32 public constant VERIFIER_ROLE  = keccak256("VERIFIER_ROLE");  // accredited verifier
    bytes32 public constant DECLARANT_ROLE = keccak256("DECLARANT_ROLE"); // authorised CBAM declarant (EU importer)

    enum Status { Pending, Verified, Revoked }

    struct Passport {
        address operator;
        string  cnCode;            // Combined Nomenclature code, e.g. "7214" (bars and rods)
        uint64  period;            // monitoring year, e.g. 2026
        uint256 quantityKg;        // batch mass
        uint256 directKg;          // direct emissions attributed to this batch (kgCO2e)
        uint256 indirectKg;        // indirect (electricity) emissions (kgCO2e)
        uint256 precursorKgCO2e;   // embedded emissions inherited from precursor passports
        bytes32 evidenceRoot;      // Merkle root of signed monitoring data (off-chain)
        bytes32 attestationHash;   // hash of verifier's hybrid (ECDSA + ML-DSA) attestation
        address verifier;
        Status  status;
        uint256 consumedKg;        // used as precursor by downstream passports
        uint256 declaredKg;        // declared into the EU by declarants
    }

    struct PrecursorUse { uint256 passportId; uint256 kg; }

    uint256 public nextId = 1;
    mapping(uint256 => Passport) private _passports;
    mapping(uint256 => PrecursorUse[]) private _precursors;
    /// passportId => declarant => embedded kgCO2e that declarant has declared into the EU
    mapping(uint256 => mapping(address => uint256)) public declaredEmbeddedBy;

    event PassportCreated(uint256 indexed id, address indexed operator, string cnCode, uint256 quantityKg, uint256 embeddedKgCO2e);
    event PassportVerified(uint256 indexed id, address indexed verifier, bytes32 attestationHash);
    event PassportRevoked(uint256 indexed id, address indexed by, string reason);
    event Declared(uint256 indexed id, address indexed declarant, uint256 kg, uint256 embeddedKgCO2e);

    error NotFound(uint256 id);
    error NotVerified(uint256 id);
    error WrongStatus(uint256 id);
    error ExceedsAvailable(uint256 id, uint256 requestedKg, uint256 availableKg);
    error SelfVerification();
    error InvalidInput();

    constructor(address admin) {
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
    }

    // ------------------------------------------------------------------ operator

    function createPassport(
        string calldata cnCode,
        uint64 period,
        uint256 quantityKg,
        uint256 directKg,
        uint256 indirectKg,
        bytes32 evidenceRoot,
        PrecursorUse[] calldata precursors
    ) external onlyRole(OPERATOR_ROLE) returns (uint256 id) {
        if (quantityKg == 0 || evidenceRoot == bytes32(0)) revert InvalidInput();

        uint256 inherited;
        for (uint256 i = 0; i < precursors.length; i++) {
            PrecursorUse calldata u = precursors[i];
            Passport storage pre = _get(u.passportId);
            if (pre.status != Status.Verified) revert NotVerified(u.passportId);
            if (u.kg == 0) revert InvalidInput();
            uint256 avail = _available(pre);
            if (u.kg > avail) revert ExceedsAvailable(u.passportId, u.kg, avail);
            pre.consumedKg += u.kg;
            inherited += (_embedded(pre) * u.kg) / pre.quantityKg;
        }

        id = nextId++;
        Passport storage p = _passports[id];
        p.operator = msg.sender;
        p.cnCode = cnCode;
        p.period = period;
        p.quantityKg = quantityKg;
        p.directKg = directKg;
        p.indirectKg = indirectKg;
        p.precursorKgCO2e = inherited;
        p.evidenceRoot = evidenceRoot;
        p.status = Status.Pending;
        for (uint256 i = 0; i < precursors.length; i++) _precursors[id].push(precursors[i]);

        emit PassportCreated(id, msg.sender, cnCode, quantityKg, _embedded(p));
    }

    // ------------------------------------------------------------------ verifier

    function verifyPassport(uint256 id, bytes32 attestationHash) external onlyRole(VERIFIER_ROLE) {
        Passport storage p = _get(id);
        if (p.status != Status.Pending) revert WrongStatus(id);
        if (p.operator == msg.sender) revert SelfVerification();
        if (attestationHash == bytes32(0)) revert InvalidInput();
        p.status = Status.Verified;
        p.verifier = msg.sender;
        p.attestationHash = attestationHash;
        emit PassportVerified(id, msg.sender, attestationHash);
    }

    /// @notice Revoke a passport (e.g. AI-flagged anomaly confirmed). Releases precursor tonnes.
    ///         A passport that has already been consumed or declared cannot be revoked silently.
    function revokePassport(uint256 id, string calldata reason) external {
        if (!hasRole(VERIFIER_ROLE, msg.sender) && !hasRole(DEFAULT_ADMIN_ROLE, msg.sender)) {
            revert AccessControlUnauthorizedAccount(msg.sender, VERIFIER_ROLE);
        }
        Passport storage p = _get(id);
        if (p.status == Status.Revoked) revert WrongStatus(id);
        if (p.consumedKg > 0 || p.declaredKg > 0) revert WrongStatus(id);
        p.status = Status.Revoked;
        PrecursorUse[] storage uses = _precursors[id];
        for (uint256 i = 0; i < uses.length; i++) {
            _passports[uses[i].passportId].consumedKg -= uses[i].kg;
        }
        emit PassportRevoked(id, msg.sender, reason);
    }

    // ------------------------------------------------------------------ declarant

    /// @notice An authorised CBAM declarant declares `kg` of this batch into the EU.
    /// @return declaredKgCO2e embedded emissions attributable to the declared mass
    function declare(uint256 id, uint256 kg) external onlyRole(DECLARANT_ROLE) returns (uint256 declaredKgCO2e) {
        Passport storage p = _get(id);
        if (p.status != Status.Verified) revert NotVerified(id);
        if (kg == 0) revert InvalidInput();
        uint256 avail = _available(p);
        if (kg > avail) revert ExceedsAvailable(id, kg, avail);
        p.declaredKg += kg;
        declaredKgCO2e = (_embedded(p) * kg) / p.quantityKg;
        declaredEmbeddedBy[id][msg.sender] += declaredKgCO2e;
        emit Declared(id, msg.sender, kg, declaredKgCO2e);
    }

    // ------------------------------------------------------------------ views

    function getPassport(uint256 id) external view returns (Passport memory) { return _get(id); }
    function getPrecursors(uint256 id) external view returns (PrecursorUse[] memory) { _get(id); return _precursors[id]; }
    function embeddedKgCO2e(uint256 id) external view returns (uint256) { return _embedded(_get(id)); }
    function availableKg(uint256 id) external view returns (uint256) { return _available(_get(id)); }

    /// @notice Specific embedded emissions in kgCO2e per tonne of product.
    function intensityPerTonne(uint256 id) external view returns (uint256) {
        Passport storage p = _get(id);
        return (_embedded(p) * 1000) / p.quantityKg;
    }

    // ------------------------------------------------------------------ internal

    function _get(uint256 id) internal view returns (Passport storage p) {
        p = _passports[id];
        if (p.operator == address(0)) revert NotFound(id);
    }

    function _embedded(Passport storage p) internal view returns (uint256) {
        return p.directKg + p.indirectKg + p.precursorKgCO2e;
    }

    function _available(Passport storage p) internal view returns (uint256) {
        return p.quantityKg - p.consumedKg - p.declaredKg;
    }
}
