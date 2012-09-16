#!/usr/bin/env python

import socket, time
from threading import Thread, Lock

from constants import *
from messages import create_messages, encode_int, decode_int, get_type
from utils import SequenceNumber
import messages

class NetworkTable(object):
    """
    The main NetworkTable class. It implements python style
    dictionary getting and setting. It contains one of the two locks
    used in this prototype.
    """
    def __init__(self, is_server):
        self.IS_SERVER = is_server
        # The entries themselves
        self.entries = {}
        # Id references to the entries
        self.ids = {}
        # The lock for the table
        self._lock = Lock()
        # The manager for the Table
        self.Manager = ConnectionManager(is_server, self)

    def __getitem__(self, key):
        "Get the value of an Entry in the table."
        return self.entries[key].value
    
    def __setitem__(self, key, val):
        "Set the value of an Entry in the table."
        self.lock()
        if key in self.entries:
            self.entries[key].value = val
        else:
            entry = Entry(key, val, self.Manager)
            self.entries[key] = entry
            if self.IS_SERVER: self.ids[entry.id] = entry
            self.Manager.write_thread.sendall(messages.MESSAGES[ENTRY_ASSIGNMENT].encode(entry))
        self.release()

    def lock(self):
        "Lock the table."
        self._lock.acquire()
    def release(self):
        "Release the lock on the table."
        self._lock.release()

class Entry(object):
    """
    Represents an Entry in the NetworkTable.
    """
    NEXT_ID = 0

    def __init__(self, name, value, manager, auto_id=True):
        self.MANAGER = manager
        self.name = name
        # The entries actual value, should be accessed as Entry().value.
        self._value = value
        self.type = get_type(value)
        # The next ID if it's a server, otherwise an UNDEFINED_ID.
        if self.MANAGER.is_server and auto_id:
            self.id = Entry.NEXT_ID
            Entry.NEXT_ID += 1
        else:
            self.id = UNDEFINED_ID
        # An indicator of whether or not this entry needs to be sent
        # over the network.
        self.dirty = False
        self.sequence_number = SequenceNumber()
        # A socket not to send it over.
        self.ignore = None

    def copy(self):
        "Create a shallow copy of the entry."
        copy = Entry(self.name, self.value, self.MANAGER, False)
        copy.__dict__ = self.__dict__
        return copy

    def _get_value(self):
        "Getter for value."
        return self._value
    def _set_value(self, value):
        "Setter for value, auto dirties and queques the entry."
        self._value = value
        self.sequence_number.increment()
        if not(self.dirty):
            self.MANAGER.add_dirty_entry(self)
        if self.id != UNDEFINED_ID:
            self.dirty = True
            self.ignore = None
    # With a property calling Entry().value calls the getter and
    # Entry().value = val calls the setter.
    value = property(_get_value, _set_value)


class ConnectionManager(object):
    """
    The connection manager handles receiving new connections and
    spinning off threads to handle them.
    """

    def __init__(self, is_server, table):
        self.TABLE = table
        self.is_server = is_server
        self.write_thread = WriteThread(is_server, self.TABLE)
        self.read_threads = []
        self.is_running = True
        self.thread = None

    def run(self, host="localhost", port=1735):
        "Create a thread running as server or client with the appropriate host and port."
        self.thread = Thread(
            target=self._run_server if self.is_server else self._run_client,
            args=(host, port)).start()

    def _run_server(self, host, port):
        "Run a server that listens and spins off connections."
        print("Server running")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((host, port))
        sock.listen(10)
        while self.is_running:
            client, _ = sock.accept()
            print("Client connected")
            self.write_thread.add(client)
            self.read_threads.append(ReadThread(client, self.is_server, self.TABLE))

    def _run_client(self, host, port):
        "Run a client that tries to connect."
        # TODO: On a failed connection, try to reconnect
        print("Client running")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        self.read_threads.append(ReadThread(sock, self.is_server, self.TABLE))
        read_thread = self.read_threads[-1]
        # TODO: Add some way of handling connections that never get initialized
        while not(read_thread.is_initialized): time.sleep(.01)
        self.write_thread.add(sock)

    def disconnect(self, sock):
        "Disconnect a socket and remove all significant references to it."
        self.write_thread.remove(sock)
        read_thread = self.get_read_thread(sock)
        self.read_threads.remove(read_thread)
        sock.close()

    def close_all(self):
        "Closes all connections and ends all threads and reset."
        self.is_running = False
        self.write_thread.close()
        for thread in self.read_threads: thread.close()
        self.write_thread = WriteThread(self.is_server)
        self.read_threads = []

    def add_dirty_entry(self, entry):
        "Add a dirty entry to the send queque."
        self.write_thread.add_dirty_entry(entry)

    def get_read_thread(self, sock):
        "Get the read thread associated with a socket."
        for thread in self.read_threads:
            if thread.sock == sock:
                return thread

class WriteThread(object):
    """
    The write thread handles writing Entry updates and other messages
    to all sockets.
    """
    # TODO: handle closed connections more gracefully.
    
    def __init__(self, is_server, table):
        self.TABLE = table
        self.is_server = is_server
        self.socks = []
        self.dirty_queque = []
        self.is_alive = True
        self._lock = Lock()
        self.thread = Thread(target=self.run).start()

    def close(self):
        "Close all sockets and stop running."
        self.is_alive = False
        for sock in self.socks:
            sock.close()

    def remove(self, sock):
        "Remove a socket from the write thread."
        if sock in self.socks: self.socks.remove(sock)

    def run(self):
        "Send updates at a regular pace to all connected sockets."
        while self.is_alive:
            entry = None
            if len(self.dirty_queque) > 0:
                self.lock()
                item = self.dirty_queque.pop(0)
                self.release()
                self.TABLE.lock()
                item.dirty = False
                entry = item.copy()
                self.TABLE.release()

            if entry != None:
                print("Sending update: {}={}".format(entry.name, entry.value))
                self.sendall(messages.MESSAGES[ENTRY_UPDATE].encode(entry), entry.ignore)
            else:
                time.sleep(.02)

    def sendall(self, message, ignore=None):
        "Send a bytearray to all sockets, possibly igoring one."
        for sock in self.socks:
            if sock != ignore:
                sock.sendall(message)

    def add(self, sock):
        "Add a socket to the write thread"
        self.socks.append(sock)
        
    def add_dirty_entry(self, entry):
        "Adds an Entry to the dirty queque."
        self.lock()
        self.dirty_queque.append(entry)
        self.release()

    def lock(self):
        "Lock for the dirty_queque"
        self._lock.acquire()

    def release(self):
        "Release lock for the dirty_queque"
        self._lock.release()

class ReadThread(object):
    """
    The read thread handles reading from a single socket.
    """
    # TODO: handle closed connections more gracefully.
    
    def __init__(self, sock, is_server, table):
        self.TABLE = table
        self.sock = sock
        self.is_server = is_server
        self.is_initialized = False
        self.in_transaction = False
        self.pending_updates = []
        self.is_alive = True
        sock.sendall(messages.MESSAGES[CLIENT_HELLO].encode())
        self.thread = Thread(target=self.run).start()
        
    def close(self):
        "Stop the read thread and close the socket."
        self.is_alive = False
        self.sock.close()

    def run(self):
        "Continuously read messages over the network."
        while self.is_alive:
            x = self.sock.recv(1)
            print "Read: " + str([x])
            msg_type = decode_int(x)
            data = messages.MESSAGES[msg_type].decode(self.sock)
            print "Read Data: " + str(data)
            if msg_type == ENTRY_ASSIGNMENT or msg_type == ENTRY_UPDATE:
                self.TABLE.lock()
                if self.in_transaction:
                    self.add_item((msg_type, data))
                else:
                    self.begin_transaction()
                    self.add_item((msg_type, data))
                    self.end_transaction()
                self.TABLE.release()

    def begin_transaction(self):
        "Begin a transaction"
        print("Beginning transaction")
        self.in_transaction = True

    def add_item(self, item):
        "Add an item to the queque of updates to send."
        self.pending_updates.append(item)
        
    def end_transaction(self):
        "End a transaction. Calls to this must lock the table."
        print("Ending transaction with {} updates.".format(len(self.pending_updates)))
        while len(self.pending_updates) > 0:
            message_type, data = self.pending_updates.pop(0)
            if message_type == ENTRY_ASSIGNMENT: self.handle_assignment(*data)
            elif message_type == ENTRY_UPDATE: self.handle_update(*data)
        self.in_transaction = False
        self.is_initialized = True

    def handle_assignment(self, name, typeof, idVal, sequence_number, value):
        self.TABLE.release()
        self.TABLE[name] = value
        self.TABLE.lock() # Avoids deadlock.
        entry = self.TABLE.entries[name]
        entry.name = name
        entry._value = value
        entry.type = typeof
        if not(self.TABLE.Manager.is_server):
            entry.id = idVal
            self.TABLE.ids[idVal] = entry
        entry.dirty = False
        entry.sequence_number = SequenceNumber(sequence_number)
        print("Added entry: {}".format(entry.__dict__))

    def handle_update(self, idVal, sequence_number, value):
        entry = self.TABLE.ids[idVal]
        if (self.TABLE.Manager.is_server and sequence_number > entry.sequence_number):
            entry.value = value
            entry.sequence_number = sequence_number
            entry.ignore = self.sock
            print("Update entry: {}={} ({})".format(entry.name, entry.value, entry.sequence_number.val))
        elif (not(self.TABLE.Manager.is_server)):
            entry._value = value
            entry.dirty = False
            entry.sequence_number = sequence_number
            entry.ignore = self.sock
            print("Update entry: {}={} ({})".format(entry.name, entry.value, entry.sequence_number.val))
        else:
            print("Rejecting update entry: {}={}".format(entry.name, value))