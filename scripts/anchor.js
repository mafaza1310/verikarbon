// Anchors the AI-checked passport on-chain:
//   1. operator creates the rebar passport from ai/out/passport_payload.json
//   2. the independent verifier approves it, committing to the integrity report hash
//   npx hardhat run scripts/anchor.js --network sepolia
const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

const explorer = (tx) => (network.name === "sepolia" ? `https://sepolia.etherscan.io/tx/${tx}` : tx);

async function main() {
  const root = path.join(__dirname, "..");
  const payloadPath = path.join(root, "ai", "out", "passport_payload.json");
  if (!fs.existsSync(payloadPath)) throw new Error("Run  python ai/build_passport.py  first.");
  const p = JSON.parse(fs.readFileSync(payloadPath));
  const dep = JSON.parse(fs.readFileSync(path.join(root, "deployments", `${network.name}.json`)));

  const verifier = dep.verifierTestnetKey
    ? new ethers.Wallet(dep.verifierTestnetKey, ethers.provider)
    : (await ethers.getSigners())[1];
  const passport = await ethers.getContractAt("CarbonPassport", dep.CarbonPassport);

  const id = await passport.nextId();
  const tx1 = await passport.createPassport(p.cnCode, p.period, p.quantityKg, p.directKg, p.indirectKg, p.evidenceRoot, []);
  await tx1.wait();
  console.log(`✔ Passport #${id} created from AI-checked monitoring data\n    ${explorer(tx1.hash)}`);

  const tx2 = await passport.connect(verifier).verifyPassport(id, p.attestationHash);
  await tx2.wait();
  console.log(`✔ Passport #${id} verified (attestation = hash of integrity report)\n    ${explorer(tx2.hash)}`);

  const intensity = await passport.intensityPerTonne(id);
  console.log(`    on-chain intensity: ${intensity} kgCO2e per tonne rebar (direct + indirect)`);

  const out = {
    network: network.name,
    passportId: Number(id),
    CarbonPassport: dep.CarbonPassport,
    CarbonPriceLedger: dep.CarbonPriceLedger,
    createTx: tx1.hash,
    verifyTx: tx2.hash,
  };
  fs.writeFileSync(path.join(root, "ai", "out", `onchain_${network.name}.json`), JSON.stringify(out, null, 2));
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
