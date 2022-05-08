import threading
import random

ELECTION_CHECK_FREQUENCY=5

def run():
    rz_term = [0, 1, 2, 4, 8][random.randint(0, 4)]
    print(ELECTION_CHECK_FREQUENCY + rz_term * ELECTION_CHECK_FREQUENCY)


for i in range(5):
    t= threading.Thread(target=run, args=())
    t.start()