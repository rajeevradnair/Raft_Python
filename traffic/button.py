# button.py
#
# This program is an internet push-button.  When you press return on
# the keyboard, it sends a UDP message to a host/port of your
# choice. That's all it does.
#
# Here's an example of code that uses it
#
#    >>> from socket import socket, AF_INET, SOCK_DGRAM
#    >>> sock = socket(AF_INET, SOCK_DGRAM)
#    >>> sock.bind(('', 12000))
#    >>> while True:
#    ...     msg, addr = sock.recvfrom(1024)
#    ...     print(msg)
#    ...
#
# With that running, go run this program in a separate terminal
# using 'python button.py localhost 12000'.  Hit return a few
# times.  You should see the above message being printed.

from socket import socket, AF_INET, SOCK_DGRAM
import sys

EW_BUTTON_PORT=12000
NS_BUTTON_PORT=13000


def main(button_id, host, port):
    sock = socket(AF_INET, SOCK_DGRAM)
    with sock:
        while True:
            try:
                line = input(f"Button {button_id}: [Press Return]")
            except EOFError:
                return
            try:
                sock.sendto(button_id.encode('ascii'), (host, port))
            except OSError:
                print("Error: Not connected")

if __name__ == '__main__':

    main("", 'localhost', NS_BUTTON_PORT)

    #if len(sys.argv) != 4:
    #    raise SystemExit(f'Usage: {sys.argv[0]} button-id host port')
    #main(sys.argv[1], sys.argv[2], int(sys.argv[3]))


        
    
