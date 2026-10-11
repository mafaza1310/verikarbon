const { expect } = require("chai");
const { ethers } = require("hardhat");

// Illustrative (synthetic) numbers for an electric-arc-furnace steel route.
const T = (tonnes) => BigInt(tonnes) * 1000n; // tonnes -> kg
const h = (s) => ethers.keccak256(ethers.toUtf8Bytes(s));

describe("VeriKarbon", function () {
  let passport, ledger, admin, mill, rollingMill, verifier, importerDE, importerNL, registry;

  beforeEach(async () => {
    [admin, mill, rollingMill, verifier, importerDE, importerNL, registry] = await ethers.getSigners();

    passport = await (await ethers.getContractFactory("CarbonPassport")).deploy(admin.address);
    ledger = await (await ethers.getContractFactory("CarbonPriceLedger")).deploy(admin.address, passport.target);

    const OP = await passport.OPERATOR_ROLE();
    await passport.grantRole(OP, mill.address);
    await passport.grantRole(OP, rollingMill.address);
    await passport.grantRole(await passport.VERIFIER_ROLE(), verifier.address);
    await passport.grantRole(await passport.DECLARANT_ROLE(), importerDE.address);
    await passport.grantRole(await passport.DECLARANT_ROLE(), importerNL.address);
    await ledger.grantRole(await ledger.REGISTRY_ROLE(), registry.address);
  });

  // billet: 10,000 t, direct 1,000 tCO2e, indirect 3,000 tCO2e  -> 0.4 tCO2e/t
  async function makeVerifiedBillet() {
    await passport.connect(mill).createPassport("7207", 2026, T(10000), T(1000), T(3000), h("billet-evidence"), []);
    await passport.connect(verifier).verifyPassport(1, h("pq-attestation-billet"));
    return 1n;
  }

  describe("passports", () => {
    it("operator cannot verify its own passport", async () => {
      await passport.grantRole(await passport.VERIFIER_ROLE(), mill.address);
      await passport.connect(mill).createPassport("7207", 2026, T(100), T(10), T(30), h("e"), []);
      await expect(passport.connect(mill).verifyPassport(1, h("a")))
        .to.be.revertedWithCustomError(passport, "SelfVerification");
    });

    it("rebar inherits precursor emissions proportionally", async () => {
      await makeVerifiedBillet();
      // rebar: 6,000 t made from 6,000 t billet, + rolling 480 t direct, 300 t indirect
      await passport.connect(rollingMill).createPassport(
        "7214", 2026, T(6000), T(480), T(300), h("rebar-evidence"), [{ passportId: 1, kg: T(6000) }]
      );
      // inherited = 4,000 t * 6,000/10,000 = 2,400 t ; total = 2,400 + 480 + 300 = 3,180 t
      expect(await passport.embeddedKgCO2e(2)).to.equal(T(3180));
      expect(await passport.intensityPerTonne(2)).to.equal(530n); // kgCO2e per tonne
      expect(await passport.availableKg(1)).to.equal(T(4000));
    });

    it("cannot consume more precursor tonnes than were produced (no double counting)", async () => {
      await makeVerifiedBillet();
      await passport.connect(rollingMill).createPassport("7214", 2026, T(6000), 0, 0, h("r1"), [{ passportId: 1, kg: T(6000) }]);
      await expect(
        passport.connect(rollingMill).createPassport("7214", 2026, T(5000), 0, 0, h("r2"), [{ passportId: 1, kg: T(5000) }])
      ).to.be.revertedWithCustomError(passport, "ExceedsAvailable");
    });

    it("unverified precursors cannot be used", async () => {
      await passport.connect(mill).createPassport("7207", 2026, T(100), T(10), T(30), h("e"), []);
      await expect(
        passport.connect(rollingMill).createPassport("7214", 2026, T(100), 0, 0, h("r"), [{ passportId: 1, kg: T(50) }])
      ).to.be.revertedWithCustomError(passport, "NotVerified");
    });

    it("revoking a pending passport releases its precursor tonnes", async () => {
      await makeVerifiedBillet();
      await passport.connect(rollingMill).createPassport("7214", 2026, T(6000), 0, 0, h("r"), [{ passportId: 1, kg: T(6000) }]);
      await passport.connect(verifier).revokePassport(2, "AI anomaly: meter reading out of physical range");
      expect(await passport.availableKg(1)).to.equal(T(10000));
    });

    it("declared tonnes and consumed tonnes share one budget", async () => {
      await makeVerifiedBillet();
      await passport.connect(importerDE).declare(1, T(7000));
      await expect(
        passport.connect(rollingMill).createPassport("7214", 2026, T(4000), 0, 0, h("r"), [{ passportId: 1, kg: T(4000) }])
      ).to.be.revertedWithCustomError(passport, "ExceedsAvailable");
    });
  });

  describe("carbon price ledger (CBAM deduction of TR-ETS price paid)", () => {
    beforeEach(async () => {
      await makeVerifiedBillet();
      // registry records: mill paid for 2,000 tCO2e, worth EUR 30,000 (illustrative)
      await ledger.connect(registry).recordPayment(mill.address, 2026, T(2000), 3_000_000n, h("tr-ets-surrender"));
      await passport.connect(importerDE).declare(1, T(5000)); // 2,000 tCO2e embedded
      await passport.connect(importerNL).declare(1, T(5000)); // 2,000 tCO2e embedded
    });

    it("lets a declarant deduct the price actually paid", async () => {
      await expect(ledger.connect(importerDE).claimDeduction(1, 1, T(1500)))
        .to.emit(ledger, "DeductionClaimed").withArgs(1, 1, importerDE.address, T(1500), 2_250_000n);
      expect(await ledger.remainingKgCO2e(1)).to.equal(T(500));
    });

    it("blocks a second importer from re-using the same payment (double deduction)", async () => {
      await ledger.connect(importerDE).claimDeduction(1, 1, T(1500));
      await expect(ledger.connect(importerNL).claimDeduction(1, 1, T(1000)))
        .to.be.revertedWithCustomError(ledger, "DoubleDeduction");
      await ledger.connect(importerNL).claimDeduction(1, 1, T(500)); // only the remainder is allowed
      expect(await ledger.remainingKgCO2e(1)).to.equal(0n);
    });

    it("blocks deducting more than the declarant actually declared", async () => {
      await ledger.connect(registry).recordPayment(mill.address, 2026, T(10000), 15_000_000n, h("big"));
      await expect(ledger.connect(importerDE).claimDeduction(2, 1, T(2001)))
        .to.be.revertedWithCustomError(ledger, "DoubleDeduction");
    });

    it("payment from another installation or year cannot be used", async () => {
      await ledger.connect(registry).recordPayment(rollingMill.address, 2026, T(100), 1n, h("other"));
      await expect(ledger.connect(importerDE).claimDeduction(2, 1, T(1)))
        .to.be.revertedWithCustomError(ledger, "Mismatch");
    });

    it("only authorised declarants can claim", async () => {
      await expect(ledger.connect(mill).claimDeduction(1, 1, T(1)))
        .to.be.revertedWithCustomError(ledger, "AccessControlUnauthorizedAccount");
    });
  });
});
