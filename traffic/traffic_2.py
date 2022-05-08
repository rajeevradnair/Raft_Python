Init = {
    'ns_light': 'G',
    'ew_light': 'R',
    'ns_button': False,
    'ew_button': False,
    'clock': 0
}


# Named states
EWGreen = lambda s: s['ew_light'] == 'G' and s['ns_light'] == 'R' and s['clock'] < 30
EWYellow = lambda s: s['ew_light'] == 'Y' and s['ns_light'] == 'R' and s['clock'] < 5
NSGreen = lambda s: s['ew_light'] == 'R' and s['ns_light'] == 'G' and s['clock'] < 60
NSYellow = lambda s: s['ew_light'] == 'R' and s['ns_light'] == 'Y' and s['clock'] < 5


def Valid(s) -> bool:
    return EWGreen(s) or EWYellow(s) or NSGreen(s) or NSYellow(s)


def Invariants(s):
    # Not both green or yellow in same direction
    assert not ((s['ns_light'] == s['ew_light']) and s['ns_light'] != 'R')
    # Light not stuck in some state forever
    assert s['clock'] <= 60