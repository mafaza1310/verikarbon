// Deploys both contracts, sets up roles, and saves addresses to deployments/<network>.json
//   npx hardhat run scripts/deploy.js --network sepolia
const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log(`Network: ${network.name}\nDeployer: ${deployer.address}`);
  console.log(`Balance: ${ethers.formatEther(await ethers.provider.getBalance(deployer.address))} ETH`);

  // A separate verifier wallet is required: the contract forbids self-verification.
  let verifier;
  if (network.name === "hardhat" || network.name === "localhost") {
    verifier = (await ethers.getSigners())[1];
  } else {
    // Throwaway TESTNET-ONLY wallet. Never reuse it on mainnet.
    verifier = ethers.Wallet.createRandom().connect(ethers.provider);
    const fund = await deployer.sendTransaction({ to: verifier.address, value: ethers.parseEther("0.003") });
    await fund.wait();
  }

  const passport = await (await ethers.getContractFactory("CarbonPassport")).deploy(deployer.address);
  await passport.waitForDeployment();
  const ledger = await (await ethers.getContractFactory("CarbonPriceLedger")).deploy(deployer.address, passport.target);
  await ledger.waitForDeployment();

  // Demo role setup: the deployer plays operator, declarant and registry; verifier is separate.
  for (const role of ["OPERATOR_ROLE", "DECLARANT_ROLE"]) {
    await (await passport.grantRole(await passport[role](), deployer.address)).wait();
  }
  await (await passport.grantRole(await passport.VERIFIER_ROLE(), verifier.address)).wait();
  await (await ledger.grantRole(await ledger.REGISTRY_ROLE(), deployer.address)).wait();

  const out = {
    network: network.name,
    CarbonPassport: passport.target,
    CarbonPriceLedger: ledger.target,
    deployer: deployer.address,
    verifier: verifier.address,
    verifierTestnetKey: verifier.privateKey || null, // testnet only
    deployedAt: new Date().toISOString(),
  };
  fs.mkdirSync(path.join(__dirname, "..", "deployments"), { recursive: true });
  fs.writeFileSync(path.join(__dirname, "..", "deployments", `${network.name}.json`), JSON.stringify(out, null, 2));

  console.log(`CarbonPassport:    ${passport.target}`);
  console.log(`CarbonPriceLedger: ${ledger.target}`);
  console.log(`Verifier wallet:   ${verifier.address}`);
}

main().catch((e) => { console.error(e); process.exitCode = 1; });
