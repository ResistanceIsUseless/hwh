"""
Curious Bolt tooling - scope library for voltage glitching.

This is the official Bolt Python library from:
https://github.com/tjclement/bolt/tree/main/lib

Usage:
    from hwh.tooling.bolt.scope import Scope
    s = Scope()
    s.glitch.repeat = 60  # Duration in 8.3ns cycles
    s.trigger()
"""

from .scope import Scope, ADCSettings, GlitchSettings, GPIOSettings

__all__ = ['Scope', 'ADCSettings', 'GlitchSettings', 'GPIOSettings']
