# Nostr Wallet Connect plugin for CLN

Allows you to create permissioned connections between your node and apps. Payment requests are sent over relays to your node.

⚠️⚠️ Not production ready! Use at your own risk. ⚠️⚠️

## Starting the Plugin

There are 3 ways to start a CLN plugin...
### Add to Your Config
Find your c-lightning config file and add

`plugin=/path/to/nwc.py`

### Manually start the plugin

`lightning-cli plugin start /path/to/nwc.py`

### Run on startup

`lightningd --plugin=/path/to/nwc.py`

## Using the plugin

`nwc-create [budget_msat] [expiry_unix]` will get you an NWC URI. This needs to be pasted into the app you are connecting with.

Apps can now send supported NIP 47 requests to your node. If the request is valid (not expired, budget not exceeded, etc.), your node will perform the requested action and return an NIP 47 response.

Keep budgets low and create new connections for each app. For now, you will have to use the `deldatastore` command to delete connections... `nwc-revoke pubkey` TBD

## Running the dev environment

### Get Nix

This project is nixified, so first make sure you have [nix installed](https://nixos.org/download) and [experimental features](https://nixos.wiki/wiki/Nix_command) turned on so that you can use the `nix develop` command.

Once nix is installed, clone the repo, and inside the project directory run:

```
nix develop
```

The first time you run this expect to wait for everything to download/build.

Now, you have **bitcoin and lightning nodes**, all the **required packages**, and **shell variables** defined!

### Start, fund, and connect your nodes

#### Start nodes in regtest

Source the [`startup_regtest.sh`](./contrib/startup_regtest.sh) script and then start 2 nodes.

```
source ./contrib/startup_regtest.sh
```

```
start_ln #default is 2 nodes
```

### Start the plugin

The [`restart_plugin.sh`](./restart_plugin.sh) script takes an _optional argument_ to specify which node you want to start the plugin on.

```
./contrib/restart_plugin.sh 1 #start the plugin on node 1
```

**NOTE**: any changes to your plugin will require you to re-run this script.

## Running the Tests

The tests are not automated right now.

What you will need to do is make sure you have two nodes running in regtest per the above instructions. When you run start_ln, you will get aliases for `l1-cli` and `l2-cli`. The value of these aliases needs to be pasted into the test files where `l2` and `baseCliCommand` are specified. 

Once you have specified the path to your node's cli, and you have 2 nodes running in your nix environment, the tests should run with `npx jest`.

WIP! Would be nice to add some CI, environment variables, etc.

## NIP-47 Supported Methods

✅ NIP-47 info event

❌ `expiration` tag in requests

✅ `get_info`
- ⚠️ block_hash not supported

✅ `pay_invoice`

✅ `pay_keysend`
- ⚠️ preimage in request not supported
- ⚠️ tlv_records in request not supported

✅ `make_invoice`
- ⚠️ description hash not supported
- ⚠️ not all tx data is returned. Missing: description, description_has, preimage, fees_paid, metadata

❌ `get_balance` - not planning to implement

❌ `lookup_invoice`

❌ `list_transactions`

❌ `multi_pay_invoice`

❌ `multi_pay_keysend`
