const { executeLightningCommand, generateRandomString } = require("./utils");
const { webln } = require("@getalby/sdk");
const crypto = require("crypto");
require("websocket-polyfill");

globalThis.crypto = crypto;

const unlimitedNwcUrl =
  "nostr+walletconnect://79be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798?relay=wss://relay.getalby.com/v1&secret=abd65865253854e8aa3e45c64a940fdc6f899c0cdff3adf5a6074a2c888db046";

const l2 =
  "/nix/store/6k1lc1cdj2qamn5nyqzbkr00m5pzr6qg-clightning-v23.11rc1/bin/lightning-cli --lightning-dir=/home/daim/code/cln/nwc/.lightning_nodes/l2";

const nwc = new webln.NostrWebLNProvider({
  nostrWalletConnectUrl: unlimitedNwcUrl,
});

beforeAll(async () => {
  await nwc.enable();
});

afterAll(() => {
  nwc.close();
});

describe("pay_invoice", () => {
  it("should pay an invoice", async () => {
    const randomString = generateRandomString();
    const l2Invoice = await executeLightningCommand(
      "invoice",
      { amount_msat: 10000, label: randomString, description: "descritption" },
      l2
    );
    if (!l2Invoice.bolt11) {
      throw new Error("Failed to create invoice");
    }
    const result = await nwc.sendPayment(l2Invoice.bolt11);
    expect(result).toHaveProperty("preimage");
  });
});

describe("make_invoice", () => {
  it("should make an invoice", async () => {
    const result = await nwc.makeInvoice({
      amount: 10000,
      description: generateRandomString(),
    });

    expect(result).toHaveProperty("paymentRequest");
  });
});

describe("get_info", () => {
  it("should return the nwc info", async () => {
    const result = await nwc.getInfo();
    expect(result).toMatchObject({
      node: expect.anything(),
      version: expect.any(String),
      supports: expect.anything(),
      methods: expect.anything(),
    });
  });
});

describe("pay_keysend", () => {
  it("should pay a node via keysend", async () => {
    const destination = await executeLightningCommand("getinfo", {}, l2);
    const result = await nwc.keysend({
      destination: destination.id,
      amount: 10000,
    });

    expect(result).toHaveProperty("preimage");
  });
});

describe("get_balance", () => {
  it("should return the node's balance", async () => {
      const balance = await nwc.getBalance();

      expect(balance).toMatchObject({
        "balance": expect.any(Number),
        "currency": "sats"
      })
  });
});

// describe("list_transactions", () => {
//   it("should return a list of transaction", async () => {
//     const result = await nwc.listTransactions();
//     expect(result).toEqual(
//       expect.arrayContaining([
//         expect.objectContaining({
//           type: expect.any(String),
//           invoice: expect.any(String),
//           description: expect.any(String),
//           description_hash: expect.any(String),
//           preimage: expect.any(String),
//           payment_hash: expect.any(String),
//           amount: expect.any(Number),
//           fees_paid: expect.any(Number),
//           settled_at: expect.any(Number),
//           created_at: expect.any(Number),
//           expires_at: expect.any(Number),
//           metadata: expect.any(Object),
//         }),
//       ])
//     );
//   });
// });

// describe("lookup_invoice", () => {
//   it("should return an invoice looked up by payment_hash", async () => {
//     const randomString = generateRandomString();
//     const l2Invoice = await executeLightningCommand(
//       "invoice",
//       { amount_msat: 10000, label: randomString, description: "descritption" },
//       l2
//     );
//     if (!l2Invoice.payment_hash) {
//       throw new Error("Failed to create invoice");
//     }
//     const result = await nwc.lookupInvoice({
//       payment_hash: l2Invoice.payment_hash,
//     });
//     expect(result).toHaveProperty("paymentRequest");
//   });
//   it("should return an invoice looked up by bolt11", async () => {
//     const randomString = generateRandomString();
//     const l2Invoice = await executeLightningCommand(
//       "invoice",
//       { amount_msat: 10000, label: randomString, description: "descritption" },
//       l2
//     );
//     if (!l2Invoice.bolt11) {
//       throw new Error("Failed to create invoice");
//     }
//     const result = await nwc.lookupInvoice({ invoice: l2Invoice.bolt11 });
//     expect(result).toHaveProperty("paymentRequest");
//   });
// });
