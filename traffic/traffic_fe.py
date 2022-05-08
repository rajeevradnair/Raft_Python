# traffic.py
#
# Implement traffic light control software.  
#
# Challenge: Can you implement it in a way that can be tested/debugged?
import asyncio
import time
from enum import Enum
from queue import Queue, Empty
from threading import Thread
from socket import *

EW_BUTTON="EW_BUTTON"
NS_BUTTON="NS_BUTTON"
NS_SIGNAL_NAME="North-South-Signal"
EW_SIGNAL_NAME="East-West-Signal"
EVENT_CLOCK_TICK="EVENT_CLOCK_TICK"
EVENT_EW_BUTTON_PUSHED="EVENT_EW_BUTTON_PUSHED"
EVENT_NS_BUTTON_PUSHED="EVENT_NS_BUTTON_PUSHED"
EW_BUTTON_PORT=12000
NS_BUTTON_PORT=13000
events_pending = Queue()
CLOCK_TICK=0.5

STATE_CONSISTENCY_LOCK = asyncio.Semaphore(1)


class States(Enum):
    NSGreen=1
    NSYellow=2
    NSRed=3
    EWGreen=4
    EWYellow=5
    EWRed=6


class TrafficLightController:
    ns_light: str
    ew_light: str
    ns_button: bool
    ew_button: bool
    clock: int

    def __init__(self, state=States.NSGreen, ns_button=False, ew_button=False, clock=0):
        self.state=state
        self.ns_button=ns_button
        self.ew_button=ew_button
        self.clock=clock

    def __str__(self):
        return f'TrafficLightController state={self.state}, nsb={self.ns_button}, ewb={self.ew_button}, clck={self.clock}'


'''
Software clock
'''


def kickoff_system_clock(controller):
    assert isinstance(controller, TrafficLightController)
    t = Thread(target=clock_tick, args=(controller,))
    t.start()
    print(f"Software clock started")


def clock_tick(controller):
    assert isinstance(controller, TrafficLightController)
    while True:
        time.sleep(CLOCK_TICK)
        events_pending.put_nowait(EVENT_CLOCK_TICK)

'''
Handlers for the various events
'''


def kickoff_event_processor(controller):
    t = Thread(target=handle_events, args=(controller,))
    t.start()
    print(f"Systems event handler (event loop) started")


def handle_events(controller):
    while True:
        try:
            event=events_pending.get_nowait()
            if event:
                if event == EVENT_NS_BUTTON_PUSHED:
                    handle_ns_button_pushed(controller)
                elif event == EVENT_EW_BUTTON_PUSHED:
                    handle_ew_button_pushed(controller)
                elif event == EVENT_CLOCK_TICK:
                    handle_clock_tick(controller)
        except Empty:
            pass


def handle_ns_button_pushed(controller):
    if controller.clock <= 15:
        events_pending.put_nowait(EVENT_NS_BUTTON_PUSHED)
    elif controller.state == States.EWGreen and controller.clock > 15:
        controller.state = States.NSGreen
        controller.ns_button = False
        controller.clock = 0
        change_light(controller.state)


def handle_ew_button_pushed(controller):
    if controller.clock <= 15:
        events_pending.put_nowait(EVENT_EW_BUTTON_PUSHED)
    elif controller.state == States.NSGreen and controller.clock > 15:
        controller.state = States.EWGreen
        controller.ew_button = False
        controller.clock = 0
        change_light(controller.state)


def handle_clock_tick(controller):
    controller.clock += 1
    print(controller)
    if controller.state == States.NSGreen and controller.clock == 60:
        controller.state = States.NSYellow
        controller.clock = 0
        change_light(controller.state)
    elif controller.state == States.NSYellow and controller.clock == 5:
        controller.state = States.EWGreen
        controller.clock = 0
        change_light(controller.state)
    elif controller.state == States.EWGreen and controller.clock == 30:
        controller.state = States.EWYellow
        controller.clock = 0
        change_light(controller.state)
    elif controller.state == States.EWYellow and controller.clock == 5:
        controller.state = States.NSGreen
        controller.clock = 0
        change_light(controller.state)


def change_light(state):
    sock=socket(AF_INET, SOCK_DGRAM)
    message = ""
    if state == States.NSGreen:
        message = NS_SIGNAL_NAME + " " + 'G'
    elif state == States.NSYellow:
        message = NS_SIGNAL_NAME + " " + 'Y'
    elif state == States.NSRed:
        message = NS_SIGNAL_NAME + " " + 'R'
    elif state == States.EWGreen:
        message = EW_SIGNAL_NAME + " " + 'G'
    elif state == States.EWYellow:
        message = EW_SIGNAL_NAME + " " + 'Y'
    elif state == States.EWRed:
        message = EW_SIGNAL_NAME + " " + 'R'
    print("message sent to the client -->", message)
    try:
        sock.sendto(message.encode('ascii'), ('localhost',10000))
    except Exception as e:
        pass
    sock.close()


'''
Kickoff hardware monitors for the buttons
'''


def kickoff_button_monitor(controller, button_id):
    port = None

    if button_id == EW_BUTTON:
        port = EW_BUTTON_PORT
    elif button_id == NS_BUTTON:
        port = NS_BUTTON_PORT

    if port:
        t = Thread(target=monitor_button, args=(controller, button_id, port,))
        t.start()
        print(f"Button {button_id} being monitored for push")
    else:
        print(f"Button monitor not initialized for {button_id}")


def monitor_button(controller, button_id, port):
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind(('localhost', port))
    while True:
        x = sock.recvfrom(100)
        print(f"received {x} for {button_id}")
        if button_id == EW_BUTTON:
            controller.ew_button = True
            events_pending.put(EVENT_EW_BUTTON_PUSHED)
        elif button_id == NS_BUTTON:
            controller.ns_button = True
            events_pending.put(EVENT_NS_BUTTON_PUSHED)


if __name__ == '__main__':
    controller = TrafficLightController()
    kickoff_event_processor(controller)
    kickoff_system_clock(controller)
    kickoff_button_monitor(controller, EW_BUTTON)
    kickoff_button_monitor(controller, NS_BUTTON)
