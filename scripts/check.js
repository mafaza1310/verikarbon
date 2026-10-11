// Checks that .env is set up correctly and Hardhat can reach Sepolia.
//   npx hardhat run scripts/check.js --network sepolia
const fs = require("fs");
const path = require("path");
const { ethers, network } = require("hardhat");

async function main() {
  const envPath = path.join(__dirname, "..", ".env");
  if (!fs.existsSync(envPath)) {
    throw new Error("No .env file found. Copy .env.example to .env (same folder as package.json) and fill it in.");
  }
  if (!process.env.SEPOLIA_RPC_URL || process.env.SEPOLIA_RPC_URL.includes("YOUR_KEY")) {
    throw new Error("SEPOLIA_RPC_URL is empty or still the example value. Use: https://ethereum-sepolia-rpc.publicnode.com");
  }
  const pk = process.env.PRIVATE_KEY || "";
  if (!/^(0x)?[0-9a-fA-F]{64}$/.test(pk)) {
    throw new Error("PRIVATE_KEY looks wrong. It must be 64 hex characters (optionally starting with 0x), with no spaces or quotes.");
  }

  const net = await ethers.provider.getNetwork();
  if (net.chainId !== 11155111n) {
    throw new Error(`Connected to chain ${net.chainId}, not Sepolia (11155111). Check SEPOLIA_RPC_URL.`);
  }
  console.log("Network OK: Sepolia");

  const [signer] = await ethers.getSigners();
  const bal = await ethers.provider.getBalance(signer.address);
  console.log(`Address:  ${signer.address}   <- must match the address shown in MetaMask`);
  console.log(`Balance:  ${ethers.formatEther(bal)} SepoliaETH`);

  if (bal < ethers.parseEther("0.01")) {
    console.log("NOT READY: get at least 0.01 SepoliaETH from a faucet, then run this again.");
  } else {
    console.log("READY: you can now run  npx hardhat run scripts/deploy.js --network sepolia");
  }
}

main().catch((e) => { console.error("PROBLEM: " + e.message); process.exitCode = 1; });
