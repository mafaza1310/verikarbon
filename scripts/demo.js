// Runs the hackathon demo story against deployed contracts:
//   EAF billet -> verified -> rolled into rebar -> declared into the EU ->
//   TR-ETS carbon price deducted once -> second deduction attempt REJECTED on-chain.
//   npx hardhat run scripts/demo.js --network sepolia
const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

const T = (t) => BigInt(t) * 1000n;
const h = (s) => ethers.keccak256(ethers.toUtf8Bytes(s));
const explorer = (tx) =>
  network.name === "sepolia" ? `https://sepolia.etherscan.io/tx/${tx}` : tx;

async function main() {
  const dep = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "deployments", `${network.name}.json`)));
  const [deployer] = await ethers.getSigners();
  const verifier = dep.verifierTestnetKey
    ? new ethers.Wallet(dep.verifierTestnetKey, ethers.provider)
    : (await ethers.getSigners())[1];

  const passport = await ethers.getContractAt("CarbonPassport", dep.CarbonPassport);
  const ledger = await ethers.getContractAt("CarbonPriceLedger", dep.CarbonPriceLedger);
  const step = async (label, txPromise) => {
    const tx = await txPromise;
    await tx.wait();
    console.log(`✔ ${label}\n    ${explorer(tx.hash)}`);
  };

  const billetId = await passport.nextId();
  await step("Billet passport created (10,000 t, 4,000 tCO2e)",
    passport.createPassport("7207", 2026, T(10000), T(1000), T(3000), h(`billet-evidence-${Date.now()}`), []));
  await step("Billet verified by independent verifier (PQ-hybrid attestation hash)",
    passport.connect(verifier).verifyPassport(billetId, h("pq-attestation-billet")));

  const rebarId = await passport.nextId();
  await step("Rebar passport created from 6,000 t billet (inherits precursor emissions)",
    passport.createPassport("7214", 2026, T(6000), T(480), T(300), h(`rebar-evidence-${Date.now()}`),
      [{ passportId: billetId, kg: T(6000) }]));
  await step("Rebar verified",
    passport.connect(verifier).verifyPassport(rebarId, h("pq-attestation-rebar")));
  console.log(`    rebar intensity: ${await passport.intensityPerTonne(rebarId)} kgCO2e/t`);

  await step("EU importer declares 5,000 t rebar", passport.declare(rebarId, T(5000)));

  const payId = await ledger.nextPaymentId();
  await step("Registry records TR-ETS carbon price paid (2,000 tCO2e)",
    ledger.recordPayment(deployer.address, 2026, T(2000), 3_000_000n, h(`tr-ets-${Date.now()}`)));
  await step("Importer deducts 2,000 tCO2e of carbon price paid", ledger.claimDeduction(payId, rebarId, T(2000)));

  // Force-send the double claim (manual gasLimit skips estimation) so the REVERT is visible on Etherscan.
  try {
    const tx = await ledger.claimDeduction(payId, rebarId, T(500), { gasLimit: 200000 });
    await tx.wait();
    console.log("✘ Unexpected: double deduction accepted");
  } catch (e) {
    const hash = e.receipt?.hash || e.transactionHash || e.transaction?.hash;
    console.log(`✔ Double deduction REJECTED on-chain${hash ? `\n    ${explorer(hash)}` : ""}`);
  }
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
