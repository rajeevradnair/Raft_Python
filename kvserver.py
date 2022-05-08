from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
from message import *
import sys

data = {}


def get(key):
    return data.get(key)


def set(key, value):
    data[key]=value


def delete(key):
    if key in data:
        del data[key]


def execute_instruction(instruction):
    if isinstance(instruction, list) and len(instruction) > 0:
        if instruction[0].upper() == "SET":
            if len(instruction) != 3:
                return f"{REQUEST_FORMAT_ERROR} - {instruction[0]}"
            set(instruction[1], instruction[2])
            return OK
        elif instruction[0].upper() == "GET":
            if len(instruction) != 2:
                return f"{REQUEST_FORMAT_ERROR} - {instruction[0]}"
            value = get(instruction[1])
            if value:
                return value
            else:
                return KEY_NOT_FOUND
        elif instruction[0].upper() == "DELETE":
            if len(instruction) != 2:
                return f"{REQUEST_FORMAT_ERROR} - {instruction[0]}"
            if instruction[1] in data:
                delete(instruction[1])
                return OK
            else:
                return KEY_NOT_FOUND
    return f"{UNRECOGNIZED_REQUEST}"


def send_message_to_client(client_socket, message_to_client):
    assert isinstance(client_socket, socket)
    assert isinstance(message_to_client, str)
    message_bytes = encode_message_for_network_transfer(message_to_client)
    send_message(client_socket, message_bytes)


def receive_message_from_client(client_socket):
    message_bytes = recv_message(client_socket)
    return decode_message_from_network(message_bytes)


def process_message_from_client(message):
    instruction = message.split()
    return instruction


def setup_server(port):
    server_socket = socket(AF_INET, SOCK_STREAM)
    server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
    server_socket.bind(('localhost', port))
    server_socket.listen()
    print(f"KV Server listening on port {port}")
    return server_socket


def teardown_server_setup(server_socket):
    assert isinstance(server_socket, socket)
    if server_socket:
        server_socket.close()


def process_client_requests(server_socket):
    assert isinstance(server_socket, socket)
    try:
        client_socket=None
        while True:
            client_socket, client_address = server_socket.accept()
            request = receive_message_from_client(client_socket)
            instruction = process_message_from_client(request)
            print("Message received from client ->", instruction)
            response_to_client = execute_instruction(instruction)
            print("     Response back to client ->", response_to_client)
            send_message_to_client(client_socket, response_to_client)
            client_socket.close()
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
        process_client_requests(server_socket)
        teardown_server_setup(server_socket)
    else:
        print(f"{REQUEST_FORMAT_ERROR} - port number is missing or not formatted correctly")