#!/usr/bin/env python3
try:
    from pyln.client import Plugin, Millisatoshi
    from coincurve import PrivateKey
    import asyncio
    import threading
    import websockets
    import uuid
    import json
    from lib import NWCOptions, NWC, ISSUED_URI_BASE_KEY
    import nip04
except Exception as e:
    print("BAD STUFF", "{}".format(e)) # TODO: if something isn't installed then disable the plugin

DEFAULT_RELAY = 'wss://relay.getalby.com/v1'

plugin = Plugin()

def pay_invoice(params: dict):
    invoice = params.get("invoice")
    if not invoice:
        # TODO: make sure this does not crash the plugin
        raise Exception("no invoice found when trying to pay :(")
    try:
        plugin.rpc.pay(bolt11=invoice)
    except Exception as e:
        plugin.log(f"{e}", 'error')
        # broadcast a error event or return error to caller
        pass

method_map = {
    "pay_invoice": pay_invoice
}

def handle_event(event):
    plugin.log(f"EVENT RECEIVED {event}")

    # p tag will be wallet pubkey because that's our only sub
    connection_key = ISSUED_URI_BASE_KEY.copy()
    connection_key.append(event.get("pubkey"))
    connection_record = plugin.rpc.listdatastore(key=connection_key)["datastore"]

    if not connection_record:
        #send UNAUTHORIZED
        return
    
    connection = json.loads(connection_record[0]["string"])

    event_content = event.get("content")

    tagged_pubkey = next((tag for tag in event.get("tags") if tag[0]=="p"), None)

    decrypted = nip04.decrypt(secret_key=connection.get('secret'), pubkey_hex=tagged_pubkey[1], data=event_content)
    decrypted_dict = json.loads(decrypted)
    print("DECRYPTED", decrypted_dict)

    method = decrypted_dict.get("method")
    method_func = method_map.get(method)
    if not method_func:
        # NOT_IMPLEMENTED
        pass

    # execute the function
    method_func(decrypted_dict.get("params"))


async def websocket_relay_connection(uri):
    subscription_id = str(uuid.uuid4())[:64]  # Generate a unique subscription ID
    filters = {
        "kinds":[23194], # Subscribe to events of kind 23194
        "#p":[plugin.rpc.getinfo().get("id")[2:]]
    }
    
    plugin.log("FILTER {}".format(filters))

    try:
        async with websockets.connect(uri) as ws:
            # send the filter to create a subscription
            await ws.send(json.dumps(["REQ", subscription_id, filters]))

            while True:
                # Wait for messages from the relay and process them
                message = await ws.recv()
                data = json.loads(message)

                if data[0] == "EVENT":
                    handle_event(data[2])
                elif data[0] == "OK":
                    pass
                elif data[0] == "CLOSED":
                    break

    except Exception as e:
        print(f"WebSocket error: {e}")
        
def start_websocket_thread(uri):
    asyncio.run(websocket_relay_connection(uri))

@plugin.init()
def init(options, configuration, plugin, **kwargs):
    uri = DEFAULT_RELAY
    websocket_thread = threading.Thread(target=start_websocket_thread, args=(uri,))
    websocket_thread.start()
    plugin.log("WebSocket thread started")

# https://github.com/benthecarman/nips/blob/nwc-extensions/47.md#nostr-wallet-connect-uri
@plugin.method("nwc-create")
def create_nwc_uri(plugin: Plugin, expiry_unix: int = None, budget_msat: int = None):
    wallet_pubkey = plugin.rpc.getinfo().get("id")[2:] # QUESTION: is this okay or should the pubkey be different from node pubkey for privacy reasons??
    relay_url = DEFAULT_RELAY

    # 32-byte hex encoded secret to sign/encrypt
    sk = PrivateKey()
    secret = sk.secret.hex()

    options = NWCOptions(
        relay_url=relay_url,
        secret=secret,
        wallet_pubkey=wallet_pubkey,
        expiry_unix=expiry_unix,
        budget_msat=Millisatoshi(budget_msat or 0)
    )

    nwc = NWC(options=options)

    data_string = json.dumps({
        "secret": nwc.secret,
        "budget_msat": nwc.budget_msat,
        "expiry_unix": nwc.expiry_unix,
        "spent_msat": Millisatoshi(0)
    })
    plugin.rpc.datastore(key=nwc.datastore_key, string=data_string)

    return {
        "url": nwc.url,
        "pubkey": nwc.pubkey
    }
    
plugin.run()
