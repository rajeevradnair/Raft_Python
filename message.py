OK = "Ok"
EMPTY_STRING=""
KEY_NOT_FOUND="Key not found"
RECOGNIZED_REQUEST="Request recognized"
UNRECOGNIZED_REQUEST="Request not recognized"
REQUEST_FORMAT_ERROR="Request format not supported"
VALUE_TYPE_NOT_SUPPORTED="Value type not supported"
REQUEST_COULD_NOT_BE_EXECUTED="Request could not be executed"
UTF_8='utf-8'


def encode_message_for_network_transfer(message, char_set=UTF_8):
    if message:
        return message.encode(char_set)


def decode_message_from_network(message_bytes, char_set=UTF_8):
    if message_bytes:
        return message_bytes.decode(char_set).strip()


def send_message(sock, msg):
    size = b'%10d' % len(msg)    # Make a 10-byte length field
    sock.sendall(size)
    sock.sendall(msg)


def recv_exactly(sock, nbytes):
    chunks = []
    while nbytes > 0:
        chunk = sock.recv(nbytes)
        if chunk == b'':
            raise IOError("Incomplete message")
            # continue
        chunks.append(chunk)
        nbytes -= len(chunk)
    return b''.join(chunks)


def recv_message(sock):
    size = int(recv_exactly(sock, 10))
    return recv_exactly(sock, size)
