#!/usr/bin/env python

import networktables as nt
import time

if __name__ == "__main__":
	table = nt.NetworkTable(False)
	try:
		print("Starting client")
		nt.create_messages(table, table.Manager)
		table.Manager.run(port=nt.PORT)
		time.sleep(2)
		while True:
			inps= raw_input("NetworkTables> ")
			if inps[0] == 'n':
				print "New item: " + x[1] + " of value: " + str(x[2])
				table[n[1]] = n[2]
			elif inps[0] == 'u':
				print "Update item: " + x[1] + " with value: " + str(x[2])
				table[n[1]] = n[2]
			elif inps[0] == 'l':
				print "List Entries:"
				for x in table.entries:
					print table[x]
	except KeyboardInterrupt as _:
		table.Manager.close_all()