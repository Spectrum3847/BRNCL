#!/usr/bin/env python

from networktables import *

def run_server():
    "Run networtables in server mode."
    try:
        print("Starting server")
        create_messages(TABLE, TABLE.Manager)
        TABLE["int"] = 1
        TABLE["foo"] = 2
        TABLE["foobar"] = 3
        TABLE.Manager.run(port=PORT)
        while True:
            #TABLE["int"] += 1
            print TABLE.entries
            for x in TABLE.entries:
                print TABLE[x]
            time.sleep(1)
    except KeyboardInterrupt as _:
        TABLE.Manager.close_all()

def run_client():
    "Run network tables client mode."
    try:
        print("Starting client")
        create_messages(TABLE, TABLE.Manager)
        TABLE.Manager.run(port=PORT)
        time.sleep(2)
        while True:
            print TABLE.entries
            for x in TABLE.entries:
                print TABLE[x]
            if "test" in TABLE.entries:
                TABLE["test"] += 1
            else:
                TABLE["test"] = 3
                print len(TABLE.entries)
            time.sleep(1)
    except KeyboardInterrupt as _:
        TABLE.Manager.close_all()

if __name__ == "__main__":
    import sys
    IS_SERVER = not("client" in sys.argv)
    TABLE = NetworkTable(IS_SERVER)
    if IS_SERVER:
        run_server()
    else:
        run_client()