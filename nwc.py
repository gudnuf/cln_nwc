#!/usr/bin/env python3

from pyln.client import Plugin

plugin = Plugin()

@plugin.init()
def init(options, configuration, plugin, **kwargs):
    plugin.log("NWC plugin initialized")

plugin.run()