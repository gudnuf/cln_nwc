# Nostr Wallet Connect plugin for CLN

⚠️⚠️ Not production ready! ⚠️⚠️

## Starting the Plugin

There are 3 ways to start a CLN plugin...
### Add to Your Config
Find your c-lightning config file and add

`plugin=/path/to/nwc.py`

### Manually start the plugin

`lightning-cli plugin start /path/to/nwc.py`

### Run on startup

`lightningd --experimental-offers --plugin=/path/to/nwc.py`

## Using the plugin

`nwc-create [budget_msat] [expiry_unix]` will get you an NWC URI.

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
