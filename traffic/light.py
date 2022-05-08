# light.py
#
# An internet connected light capable of displaying three colors (R,
# G, B).  You pick a port number and send it a message via UDP to
# change the color.  That's all it does.
#
# If running on port 10000, here's an example of how you communicate
# with it.
#
#    >>> from socket import socket, AF_INET, SOCK_DGRAM
#    >>> sock = socket(AF_INET, SOCK_DGRAM)
#    >>> sock.sendto(b'G', ('localhost', 10000))
#    >>>
#
# Try sending messages such as b"R" or b"Y". You should see the
# output change.

from socket import socket, AF_INET, SOCK_DGRAM
import sys

codes = {
    'G': '\x1b[32m',
    'R': '\x1b[31m',
    'Y': '\x1b[33m',
}


def main(label, port):
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(('', port))
    display_label = label
    display_light = 'R'
    while True:
        sys.stdout.write(f'\r{codes[display_light]}{display_label} {display_light}\x1b[0m')
        sys.stdout.flush()
        msg, addr = sock.recvfrom(8192)
        msg = msg.decode('ascii')
        display_label = msg.split()[0]
        display_light = msg.split()[1]
        # if display_light in {'G', 'Y', 'R'}:
        #    display_light = msg


if __name__ == '__main__':
    import os
    # if len(sys.argv) != 3:
    #    raise SystemExit(f'Usage: {sys.argv[0]} label port')
    # os.system('')  # Windows hack. Don't ask.
    # main(sys.argv[1], int(sys.argv[2]))
    main("East-West Y", 10000)
