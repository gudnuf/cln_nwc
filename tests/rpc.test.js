const { executeLightningCommand } = require("./utils");

const baseCliCommand =
  "/nix/store/6k1lc1cdj2qamn5nyqzbkr00m5pzr6qg-clightning-v23.11rc1/bin/lightning-cli --lightning-dir=/home/daim/code/cln/nwc/.lightning_nodes/l1";

describe("RPC tests", () => {
  describe("nwc-create", () => {
    it("should return an nwc url", async () => {
      const result = await executeLightningCommand("nwc-create", {}, baseCliCommand);
      expect(result).toHaveProperty("url");
    });

    it("should accept expiry_unix and budget_msat arguments", async () => {
      const result = await executeLightningCommand("nwc-create", {
        expiry_unix: 1000000000,
        budget_msat: 1000000,
      }, baseCliCommand);
      expect(result).toHaveProperty("url");
    });
  });
});
