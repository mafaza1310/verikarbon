# VeriKarbon — Setup on Windows (step by step)

Time needed: about 1 hour the first time.

## 1. Install tools (once)

1. **Node.js 22 LTS** — download the Windows installer from https://nodejs.org and install with defaults.
   Check in a new terminal (PowerShell or the PyCharm terminal):
   ```
   node -v
   npm -v
   ```
2. **Git** — https://git-scm.com/download/win (defaults are fine).
3. **MetaMask** browser extension — https://metamask.io
   - Create a **new account used only for this project**. Never put real money in it.
   - In MetaMask, turn on "Show test networks" and select **Sepolia**.

## 2. Open the project

1. Unzip `verikarbon.zip`, e.g. to `C:\Projects\verikarbon`.
2. In PyCharm: *File → Open* → choose that folder. Open the terminal at the bottom.
3. Install dependencies:
   ```
   npm install
   ```
4. Run the tests (this downloads the Solidity compiler the first time):
   ```
   npx hardhat test
   ```
   You should see **11 passing**. If so, the core of the project works on your machine.

## 3. Get free testnet ETH and an RPC URL

1. **RPC URL**: create a free account at https://dashboard.alchemy.com → *Create app* → network **Ethereum Sepolia** → copy the HTTPS URL.
2. **Test ETH**: copy your MetaMask address and request Sepolia ETH from a faucet, e.g. the Google Cloud Web3 faucet (search "Google Cloud Sepolia faucet"). 0.05 ETH is plenty.
   Some faucets require a small mainnet balance; if one refuses, try another.

## 4. Configure secrets

1. Copy `.env.example` to `.env` (same folder).
2. Fill in:
   - `SEPOLIA_RPC_URL` = the Alchemy URL
   - `PRIVATE_KEY` = MetaMask → account menu → *Account details* → *Show private key* (testnet account only!)
3. `.env` is in `.gitignore`, so it will **not** be uploaded to GitHub. Double-check before every push.

## 5. Deploy and run the demo

```
npx hardhat run scripts/deploy.js --network sepolia
npx hardhat run scripts/demo.js --network sepolia
```

The demo prints an Etherscan link for every step, ending with the **rejected double deduction**.
Copy the two contract addresses into `README.md` → *Deployed contracts*.

## 6. Publish to GitHub

1. Create a **public** repository named `verikarbon` on https://github.com (no README, it already has one).
2. In the terminal:
   ```
   git init
   git add .
   git status            # make sure .env is NOT listed
   git commit -m "Smart-contract core: passports + once-only carbon price deduction"
   git branch -M main
   git remote add origin https://github.com/<your-username>/verikarbon.git
   git push -u origin main
   ```

## If something fails

Copy the full error message and send it to Claude — most first-time problems are a missing `.env` value or no test ETH.
