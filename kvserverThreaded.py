# Find and kill process in Windows using Powershell cmdlets:
# Get-Process -Id (Get-NetTCPConnection -LocalPort 14000).OwningProcess
# Get-Process -Id (Get-NetTCPConnection -LocalPort 15000).OwningProcess
# Get-Process -Id (Get-NetTCPConnection -LocalPort 16000).OwningProcess
# Get-Process -Id (Get-NetTCPConnection -LocalPort 17000).OwningProcess
# Get-Process -Id (Get-NetTCPConnection -LocalPort 18000).OwningProcess
# Stop-Process -Id pid



import threading
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from message import *
import sys
from threading import Thread
import raft
import instructions

data = {}
LOCALHOST_ADDR='localhost'


def get(key):
    return data.get(key)


def set(key, value):
    data[key]=value


def delete(key):
    if key in data:
        del data[key]


def execute_instruction(instruction):
    if isinstance(instruction, list) and len(instruction) > 0:
        if instruction[0].upper() == instructions.SET_COMMAND:
            if len(instruction) != 3:
                return f"{REQUEST_FORMAT_ERROR} - {instruction[0]}"
            set(instruction[1], instruction[2])
            return OK
        elif instruction[0].upper() == instructions.GET_COMMAND:
            if len(instruction) != 2:
                return f"{REQUEST_FORMAT_ERROR} - {instruction[0]}"
            value = get(instruction[1])
            if value:
                return value
            else:
                return KEY_NOT_FOUND
        elif instruction[0].upper() == instructions.DELETE_COMMAND:
            if len(instruction) != 2:
                return f"{REQUEST_FORMAT_ERROR} - {instruction[0]}"
            if instruction[1] in data:
                delete(instruction[1])
                return OK
            else:
                return KEY_NOT_FOUND
        elif instruction[0].upper() == instructions.NO_OP_COMMAND:
            return OK
    return f"{UNRECOGNIZED_REQUEST}"


def send_message_to_client(client_socket, message_to_client):
    assert isinstance(client_socket, socket)
    assert isinstance(message_to_client, str)
    message_bytes = encode_message_for_network_transfer(message_to_client)
    send_message(client_socket, message_bytes)


def receive_message_from_client(client_socket):
    message_bytes = recv_message(client_socket)
    return decode_message_from_network(message_bytes)


def extract_instruction_from_message(message):
    instruction = message.split()
    return instruction


def translate_instruction_to_message(instruction):
    return " ".join(instruction)


def setup_server(port):
    server_socket = socket(AF_INET, SOCK_STREAM)
    server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
    server_socket.bind((LOCALHOST_ADDR, port))
    server_socket.listen()
    print(f"KV Server listening @ {LOCALHOST_ADDR}:{port}")
    return server_socket


def teardown_server_setup(server_socket):
    assert isinstance(server_socket, socket)
    if server_socket:
        server_socket.close()


def process_client_request(client_socket):
    assert isinstance(client_socket, socket)
    try:
        request = receive_message_from_client(client_socket)
        instruction = extract_instruction_from_message(request)
        assert isinstance(instruction, list)


        # This is where RAFT consensus code will need to be inserted
        # log the instruction in the local log
        # send the translated instruction to followers for log
        raft_consensus = True #raft.obtain_consensus()

        if raft_consensus:
            # Execute instruction does an actual state change
            response_to_client = execute_instruction(instruction)
            print(f"[Thread-{threading.get_ident()}] Message received from client {client_socket.getpeername()} -> {instruction} || Response back to client -> {response_to_client}")
            send_message_to_client(client_socket, response_to_client)
        else:
            send_message_to_client(client_socket, REQUEST_COULD_NOT_BE_EXECUTED)
        client_socket.close()
    except IOError:
        if client_socket:
            client_socket.close()


def process_client_requests_loop(server_socket):
    assert isinstance(server_socket, socket)
    try:
        while True:
            client_socket, client_address = server_socket.accept()
            t = Thread(target=process_client_request, args=(client_socket,))
            t.start()
    except IOError:
        if client_socket:
            client_socket.close()


def process_command_line_args(args):
    if len(args) >=2 :
        return int(args[1])


if __name__ == '__main__':
    port = process_command_line_args(sys.argv)
    if port:
        server_socket = setup_server(port)
        process_client_requests_loop(server_socket)
        teardown_server_setup(server_socket)
    else:
        print(f"{REQUEST_FORMAT_ERROR} - port number is missing or not formatted correctly")