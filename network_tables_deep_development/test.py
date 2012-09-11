#!/usr/bin/env python

from networktables import *

if __name__ == "__main__":
    import sys
    IS_SERVER = not("client" in sys.argv)
    if IS_SERVER:
        run_server()
    else:
        run_client()

import networktables
from pycana import CodeAnalyzer
analyzer= CodeAnalyzer(networktables)
relations= analyzer.analyze()
analyzer.draw_relations(relations, 'class_diagram.png')