import sys
from socket import socket, AF_INET, SOCK_STREAM
from message import *

LOCALHOST_ADDR='localhost'
SERVER_PORT=12344

def send_message_to_server(client_socket, message):
    mb = encode_message_for_network_transfer(message)
    send_message(client_socket, mb)


def receive_message_from_server(client_socket):
    message_bytes = recv_message(client_socket)
    return decode_message_from_network(message_bytes)


def create_connection_to_server():
    client_socket = socket(AF_INET,SOCK_STREAM)
    client_socket.connect((LOCALHOST_ADDR,SERVER_PORT))
    return client_socket


def close_connection_to_server(client_socket):
    assert isinstance(client_socket, socket)
    if client_socket:
        client_socket.close()


def send_receive(client_socket, message):
    send_message_to_server(client_socket, message.strip())
    message_from_server = receive_message_from_server(client_socket)
    print(message_from_server)


def process_command_line_args(args):
    c = ""
    for i in range(1, len(args)):
        c = c + str(args[i]) + " "
    return c.strip()


if __name__ == '__main__':
    request = process_command_line_args(sys.argv)
    if request != "":
        client_socket = create_connection_to_server()
        send_receive(client_socket, request)
        close_connection_to_server(client_socket)
    else:
        print(f"{REQUEST_FORMAT_ERROR} - Instructions to the Key-Value server(s) is missing")