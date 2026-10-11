# VeriKarbon

**Tamper-evident embedded-emissions passports and once-only carbon-price deductions for CBAM exporters.**

Track: **Carbon Markets & Emissions Transparency** — IEEE ClimateChain Global Hackathon 2026

> Status: work in progress (smart-contract core complete and tested; AI layer and dashboard in progress).

## The problem

Since 1 January 2026 the EU Carbon Border Adjustment Mechanism (CBAM) is in its definitive phase: EU importers of steel, cement, aluminium, fertilisers, electricity and hydrogen pay for the emissions embedded in those goods. Exporters who cannot prove their actual emissions are charged with default values, which are much higher, so a cleaner plant gets no reward for being cleaner. At the same time, CBAM lets importers deduct a carbon price already paid in the country of origin, and Türkiye's national ETS creates exactly such a price. Without a shared record, one domestic payment could be deducted more than once, and precursor emissions can be lost or counted twice as goods move along the supply chain.

The parties involved (exporter, accredited verifier, EU importer, national registry) do not fully trust each other, and no single one of them should own the database. That is the case where a blockchain is the right tool.

## What the contracts guarantee

| Contract | Guarantee |
|---|---|
| `CarbonPassport` | One non-transferable passport per production batch. Precursor emissions are inherited proportionally. A batch's tonnes can be consumed downstream **or** declared into the EU, never more than were produced. An operator can never verify its own passport. Only hashes go on-chain. |
| `CarbonPriceLedger` | Carbon price paid at origin can be deducted **once**: total deductions ≤ emissions the payment covered, and each declarant ≤ embedded emissions it actually declared. Installation and year must match. |

## Architecture (planned full system)

1. **Signed data at source** — meter/fuel/precursor data, hashed into a Merkle root.
2. **AI layer** — anomaly detection + physical plausibility checks; verification-readiness score; cited RAG assistant over official CBAM / TR-ETS texts.
3. **Verifier attestation** — hybrid ECDSA + ML-DSA (post-quantum) signature; hash anchored on-chain.
4. **Smart contracts** — this repository's `contracts/`.
5. **Dashboard** — default-value vs. verified CBAM cost per shipment.

All plant data in this prototype is **synthetic and labelled as such**.

## Run it

```bash
npm install
npx hardhat test                                    # 11 tests
npx hardhat run scripts/deploy.js --network sepolia
npx hardhat run scripts/demo.js   --network sepolia
```

See `SETUP_WINDOWS.md` for a step-by-step guide.

## Deployed contracts (Sepolia)

- CarbonPassport: [`0x152833ef8e128d6e9B4a45Ef4b0E58E53D829F11`](https://sepolia.etherscan.io/address/0x152833ef8e128d6e9B4a45Ef4b0E58E53D829F11)
- CarbonPriceLedger: [`0xfef27094C25d71B22F50059EAb44c292b2C08618`](https://sepolia.etherscan.io/address/0xfef27094C25d71B22F50059EAb44c292b2C08618)

### Live demo transactions (one rebar shipment, Türkiye → EU)

| Step | Transaction |
|---|---|
| Billet passport created (10,000 t, 4,000 tCO2e) | [tx](https://sepolia.etherscan.io/tx/0x88c3e37f9b7d8c50724f5610d91fb702d3351d28aad770b84ab1cc1b5a3199b4) |
| Billet verified by independent verifier | [tx](https://sepolia.etherscan.io/tx/0x0c87d470f4dc7cda9599ba838eccd047ada420d02686731997503f57dc63eaa2) |
| Rebar passport created from 6,000 t billet (inherits emissions) | [tx](https://sepolia.etherscan.io/tx/0x90b5f1d87515f0e0c2d165c55b873ef8dcae76ca1f27756c7542f6a1dc34c884) |
| Rebar verified (530 kgCO2e/t) | [tx](https://sepolia.etherscan.io/tx/0xfac0a0143663c076eafccd98229eee731b5f9b65d489b1a9743704f81fe14579) |
| EU importer declares 5,000 t rebar | [tx](https://sepolia.etherscan.io/tx/0x7637090fc6d0139c96ab83999370de14ba7a285a2c8e7ecadb5b8bfd8e26e2da) |
| Registry records TR-ETS carbon price paid (2,000 tCO2e) | [tx](https://sepolia.etherscan.io/tx/0xd5de91806ad94c2883ba194f286787a6ac8b2ffed841f6219833a28edc790847) |
| Importer deducts 2,000 tCO2e of carbon price paid | [tx](https://sepolia.etherscan.io/tx/0x38fa88a29dfc90a35b1fb7b026f359a73832c8db65a3b590b23c99b843d95d7e) |
| **Second deduction of the same payment → rejected on-chain** | [tx (failed)](https://sepolia.etherscan.io/tx/0x7839fe23b0613e4877cfe5fa02d083a8022d5885834c719aff946b24b3824a5b) |

## License

MIT
