import sys
import threading
import time
from enum import Enum
from queue import Queue, Empty
import uuid
import pickle
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
import time
import instructions
import random
from datetime import datetime


import message

LOG_APPEND_FAILURE = -1
LOG_APPEND_SUCCESS = 0

NUM_OF_SERVERS = 5


class Servers(Enum):
    Server_0 = 0
    Server_1 = 1
    Server_2 = 2
    Server_3 = 3
    Server_4 = 4


_id_to_servers = {
    0: Servers.Server_0,
    1: Servers.Server_1,
    2: Servers.Server_2,
    3: Servers.Server_3,
    4: Servers.Server_4
}

SERVER_ADDRESSES = {
    Servers.Server_0: ('127.0.0.1', 14000),
    Servers.Server_1: ('127.0.0.1', 15000),
    Servers.Server_2: ('127.0.0.1', 16000),
    Servers.Server_3: ('127.0.0.1', 17000),
    Servers.Server_4: ('127.0.0.1', 18000),
}


class RaftServerRole(Enum):
    LEADER = 0
    CANDIDATE = 1
    FOLLOWER = 2


class RaftServer:

    INIT_INDEX = -1

    def __init__(self, id, current_term=0, role=RaftServerRole.FOLLOWER, leader=None):
        self.id = id
        self.current_term = current_term
        self.role = role
        self.log = RaftPersistentLog(self)
        self.next_index = []
        self.match_index = []
        self.last_applied_index = self.INIT_INDEX

    def fetch_peer_ids(self):
        peers = []
        for i in range(NUM_OF_SERVERS):
            peer_server_id = _id_to_servers[i]
            if self.id == peer_server_id:
                continue
            peers.append(peer_server_id)
        return peers

    def index_state(self):
        return f'{self.id}-{self.role} | leader ={self.leader} | curr_term={self.current_term} | commitIndex={self.log.last_committed_index} | lastAppliedIndex = {self.last_applied_index}'

    def __repr__(self):
        return f'{self.id} / term={self.current_term} / {self.role} / leader={self.leader}'


class LogEntry:

    def __init__(self, command, term, inserted_by):
        self.term = term
        self.command = command
        self.inserted_by = inserted_by

    def __repr__(self):
        return f'[term={self.term} | {self.command} ]'
        # return f'[term={self.term} | {self.command} | o={self.inserted_by} ]'


class RaftPersistentLog:
    INIT_INDEX = -1

    def __init__(self, owner_server):
        assert isinstance(owner_server, RaftServer)
        self.log_entries = []
        self.server = owner_server
        self.last_committed_index = self.INIT_INDEX

    def dump(self):
        print(f'{log.server.id} - {log.server.role}')
        print(f'        log [{len(self.log_entries)} items] => {self.log_entries}')


class RaftMessage:

    def __init__(self, uuid, source, destination, ref_msg_uuid=None):
        self.uuid = uuid
        self.source = source
        self.destination = destination
        self.ref_msg_uuid = ref_msg_uuid

    def __repr__(self):
        return f'{self.source} -> {self.destination} / uuid= {self.uuid}'


class ClientAppendRequest(RaftMessage):
    def __init__(self, command, uuid, source, destination, ref_msg_uuid=None):
        super().__init__(uuid, source, destination, ref_msg_uuid)
        self.command = command

    def __repr__(self):
        return f'ClientAppendRequest -> {super().__repr__()} / commands -> {self.command}'


class ClientAppendResponse(RaftMessage):
    def __init__(self, uuid, source, destination, ref_msg_uuid=None):
        super().__init__(uuid, source, destination, ref_msg_uuid)

    def __repr__(self):
        return f'ClientAppendResponse -> {super().__repr__()}'


class TriggerCommit(RaftMessage):

    def __init__(self, uuid, source, destination):
        super().__init__(uuid, source, destination)

    def __repr__(self):
        return f'TriggerCommit -> {super().__repr__()}'


class ElectionTimeout(RaftMessage):

    def __init__(self, uuid, source, destination):
        super().__init__(uuid, source, destination)

    def __repr__(self):
        return f'ElectionTimeout -> {super().__repr__()}'


class HeartBeatTick(RaftMessage):

    def __init__(self, uuid, source, destination):
        super().__init__(uuid, source, destination)

    def __repr__(self):
        return f'HeartBeatTick -> {self.source}'


class AppendEntriesRequest(RaftMessage):
    def __init__(self, leader_term, leader_id, leader_prev_log_index, leader_prev_log_term, entries_to_be_appended,
                 leader_last_commit_index, uuid, source, destination, ref_msg_uuid=None):
        super().__init__(uuid, source, destination, ref_msg_uuid)
        self.leader_term = leader_term
        self.leader_id = leader_id
        self.leader_prev_log_index = leader_prev_log_index
        self.leader_prev_log_term = leader_prev_log_term
        self.entries_to_be_appended = entries_to_be_appended
        self.leader_last_commit_index = leader_last_commit_index

    def __repr__(self):
        return f'AppendEntriesRequest -> {super().__repr__()} / {self.leader_id} / prev_term={self.leader_prev_log_term} / prev_index={self.leader_prev_log_index} / {self.entries_to_be_appended}'


class AppendEntriesResponse(RaftMessage):
    def __init__(self, follower_current_term, success, match_index, uuid, source, destination, ref_msg_uuid=None):
        super().__init__(uuid, source, destination, ref_msg_uuid)
        self.success = success
        self.follower_current_term = follower_current_term
        self.match_index = match_index

    def __repr__(self):
        return f'AppendEntriesResponse -> follower_term={self.follower_current_term} / success = {self.success} / ref={self.ref_msg_uuid}'


def register_leader_last_contact(runtime, server, obj):
    assert isinstance(obj, AppendEntriesRequest)

    runtime.last_AppendEntriesRequest_time = time.time()
    runtime.last_AppendEntriesRequest_leader = obj.leader_id
    runtime.last_AppendEntriesRequest_leader_term = obj.leader_term


'''
election timeout process
'''


def kickoff_election_timeout_checker(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    t = threading.Thread(target=election_timeout_checker, args=(runtime, server,))
    print(f'{server.id} -> started Election Timeout -> Handler loop')
    t.start()


def election_timeout_checker(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    # TODO: this is a testing artifact and should be removed
    if runtime.fast_track and server.id == Servers.Server_0:
        runtime.fast_track = False
        runtime.make_leader(server)
        server.current_term += 1
        return

    while True:

        # Enter only if you are a follower
        if server.role == RaftServerRole.LEADER:
            continue

        # DO NOT ASK ME WHY - TODO need to think about distributed randomness
        rz_term = [0, 2, 4, 8, 16][random.randint(0, 4)]
        wait_period = runtime.ELECTION_CHECK_FREQUENCY + rz_term * runtime.ELECTION_CHECK_FREQUENCY
        # print(f'{server.id}-{server.role} waiting for {wait_period} secs before checking for election timeout')
        time.sleep(wait_period)

        # assume no election timeout and then proceed to check if election timeout occurred
        election_timeout_occurred = False
        election_timeout_duration = time.time() - runtime.last_AppendEntriesRequest_time

        # print(f'duration -> {election_timeout_duration}, threshold -> {runtime.LEADER_CHECKIN_MAX_WAIT}')
        if election_timeout_duration > runtime.LEADER_CHECKIN_MAX_WAIT:
            election_timeout_occurred = True

        # Election timeout has occurred
        if not election_timeout_occurred:
            pass

        else:
            # print(f'{server.id} detected an election_timeout')

            # transition to a candidate
            runtime.role_change_follower_to_candidate(server)

            # fetch candidate's peers
            # request for votes from peers parallely
            peer_ids = server.fetch_peer_ids()
            peer_responses = {server.id:True}
            pts = []
            for peer_id in peer_ids:
                # for each peer, request vote
                t = threading.Thread(target=request_for_vote, args=(runtime, server, peer_id, peer_responses,))
                pts.append(t)
                t.start()
            # wait for responses from all threads
            for pt in pts:
                pt.join()

            vote_count = list(peer_responses.values()).count(True)
            print(f'{server.id} got a total of {vote_count} votes -> {peer_responses}')

            # check the response status
            if vote_count > (NUM_OF_SERVERS // 2):

                # make a new leader
                runtime.make_leader(server)

                # TODO - want to introduce this code <safety net>, but right now going aggressive with LEADER transition
                '''
                # received required responses, but want to double-check if election timeout is ON before becoming a leader
                if time.time() - runtime.last_AppendEntriesRequest_time > runtime.LEADER_CHECKIN_MAX_WAIT:

                    # becoming a leader
                    runtime.make_leader(server)

                else:

                    # a new leader got appointed in between -> become a follower and check for election timeout again
                    runtime.role_change_candidate_to_follower(server)
                '''

            else:

                # did not receive enough votes -> become a follower and check for election timeout again
                runtime.role_change_candidate_to_follower(server)


def request_for_vote(runtime, candidate, peer_id, peer_responses):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(candidate, RaftServer)

    if len(candidate.log.log_entries) == 0:
        candidate_last_log_term = 0
    else:
        candidate_last_log_term = candidate.log.log_entries[len(candidate.log.log_entries)-1].term

    # package VoteRequest to be sent to the peer
    request_msg = VoteRequest(candidate_id=candidate.id,
                              candidate_term=candidate.current_term,
                              candidate_last_log_index=len(candidate.log.log_entries)-1,
                              candidate_last_log_term=candidate_last_log_term,
                              candidate_log_len=len(candidate.log.log_entries),
                              uuid=runtime.gen_uuid(),
                              source=candidate.id,
                              destination=peer_id,
                              ref_msg_uuid=None)

    # send VoteRequest to the peer
    runtime.outgoing_queue.put_nowait(request_msg)

    time.sleep(1)

    # wait for VoteResponse back from the peer
    response_msg = runtime.return_message_from_incoming_queue_with_ref_uuid(message_type=VoteResponse, uuid_to_check=request_msg.uuid)

    # update responses dictionary with response from the specific peer
    if response_msg:
        assert isinstance(response_msg, VoteResponse)
        # TODO - what about the term in the VoteResponse
        peer_responses[peer_id] = response_msg.vote_granted
    else:
        peer_responses[peer_id] = False
    # print(f'Peer={peer_id} gave {"None" if response_msg is None else response_msg}')


def grant_vote(runtime, server, msg):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(msg, VoteRequest)

    # initialize VoteResponse to 'No Vote'
    response_msg = VoteResponse(vote_granted=False, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)
    # print("\n\n")
    # print(f'Candidate {msg.candidate_id} requesting a vote for {msg.candidate_term}')
    # print(f'Voted for dictionary -> {runtime.voted_for}')

    # If I have already voted in the past for requested term
    if runtime.voted_for.get(msg.candidate_term):

        # peer already voted for the same candidate
        if runtime.voted_for[msg.candidate_term] == msg.candidate_id:
            response_msg = VoteResponse(vote_granted=True, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)
            # print(f'............................. Stage 0 <Already voted> for {runtime.voted_for[msg.candidate_term]}')

        # peer voted for some other candidate
        else:
            # print(f'............................. Stage 1 <NO VOTE - Already voted> for {runtime.voted_for[msg.candidate_term]}')
            response_msg = VoteResponse(vote_granted=False, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)

    # I have not voted in the past for the requested term
    else:

        # candidate' last log term is less than my current term, so I cannot vote for the candidate
        if msg.candidate_last_log_term < server.current_term:
            response_msg = VoteResponse(vote_granted=False, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)

            # print(f'............................. Stage 2 - NO VOTE')

        # candidate' last log term is greater than my current term, I will vote for the candidate
        if msg.candidate_last_log_term > server.current_term:
            runtime.voted_for[msg.candidate_term] = msg.candidate_id
            response_msg = VoteResponse(vote_granted=True, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)
            # print(f'............................. Stage 3 - VOTE')

        # candidate and I are at the same term level
        if msg.candidate_last_log_term == server.current_term:

            # I will vote for the candidate, since candidate has a longer log
            if msg.candidate_log_len >= len(server.log.log_entries):  # TODO ***************** > or >= think about it
                runtime.voted_for[msg.candidate_term] = msg.candidate_id
                response_msg = VoteResponse(vote_granted=True, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)
                # print(f'............................. Stage 4 - VOTE {response_msg}')

            # I will not vote for the candidate, since I have a longer log
            else:
                response_msg = VoteResponse(vote_granted=False, peer_term=server.current_term, uuid=runtime.gen_uuid(), source=server.id, destination=msg.candidate_id, ref_msg_uuid=msg.uuid)
                # print(f'............................. Stage 5 - NO VOTE')

    runtime.outgoing_queue.put_nowait(response_msg)


'''
follower appending entries
'''


def handle_append_entries(runtime, server, msg):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(msg, AppendEntriesRequest)

    # print(f'Received append entries request -> {msg.entries_to_be_appended} {msg.uuid}')

    # Reject AppendEntriesRequest if the leader term in the message < my current term
    # i.e. leader entries are stale
    if msg.leader_term < server.current_term:
        # put a failure AppendEntriesResponse to the queue
        response_msg = AppendEntriesResponse(follower_current_term=server.current_term,
                                             success=False,
                                             match_index=server.INIT_INDEX,
                                             uuid=runtime.gen_uuid(),
                                             source=server.id,
                                             destination=msg.source,
                                             ref_msg_uuid=msg.uuid)
        runtime.outgoing_queue.put_nowait(response_msg)
        return

    # Process since the leader term >= my own term

    # append entries locally and inform the leader with AppendEntriesResponse
    _s, _t, _i = append_entries(runtime, server, msg.leader_prev_log_index, msg.leader_prev_log_term,
                                msg.entries_to_be_appended)

    # put a successful AppendEntriesResponse to the queue
    response_msg = AppendEntriesResponse(follower_current_term=_t,
                                         success=_s,
                                         match_index=msg.leader_prev_log_index + len(msg.entries_to_be_appended),
                                         uuid=runtime.gen_uuid(),
                                         source=server.id,
                                         destination=msg.source,
                                         ref_msg_uuid=msg.uuid)
    runtime.outgoing_queue.put_nowait(response_msg)

    # additionally, the follower takes the leader's last_committed_index from the AppendEntriesRequest and updates its commit index
    if _s:

        # update the latest term the follower has seen and accepted (in terms of AppendEntriesRequest) from the leader
        server.current_term = msg.leader_term

        # update follower's last_commit_index
        old_commit_index = server.log.last_committed_index

        # the new commit index of the follower = leader's last_committed_index as long as
        # it is within follower' valid log index range. Hence, the min()
        new_commit_index = min(msg.leader_last_commit_index, len(server.log.log_entries) - 1)

        # commit index always move forward
        if new_commit_index > server.log.last_committed_index:
            server.log.last_committed_index = new_commit_index

            # apply the to-be-applied commands and update the state machine of the follower
            update_state_machine(runtime, server, old_commit_index + 1, new_commit_index)


'''
After a commit, update the state machine of the server (applicable to both leader and follower)
For this method, you need the index of the first command yet to be applied i.e. the start_commit_index
and the index of the last command to be applied i.e. end_commit_index
'''


def update_state_machine(runtime, server, start_commit_index, end_commit_index):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    # iterate through each command to be applied to the state machine
    # +1 since range() does an implicit -1 on the second term
    for i in range(start_commit_index, end_commit_index + 1):
        log_entry = server.log.log_entries[i]
        assert isinstance(log_entry, LogEntry)
        if runtime.application:
            runtime.application.apply_to_state_machine(log_entry.command)
        else:
            pass
            # print(f' [ERROR] RaftRuntime has no reference to an application. The application needs to be set ..... ')
        # set the server's last_applied_index
        server.last_applied_index = i
    pass


'''
handle commit entries on the leader
'''


def handle_leader_commit_entries(runtime, server, match_index):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(match_index, list)

    # temporarily save the leader' current commit index
    old_commit_index = server.log.last_committed_index

    # *** COMPUTE THE NEW COMMIT INDEX FOR THE LEADER ***
    # Leader's commit index is derived from the match indices of the followers
    # The idea is that if the leader was committing, it implies it has received consensus from atleast (NUM_OF_SERVERS//2+1) servers
    # So you sort the match_index array and find the median of the sorted list which will be the leader's new commit index
    # example: suppose after backtracking your match_index[] were either example-1 or example-2
    #               example-1 - match_index = [0,8,4,5,6] -> sorted -> [0,4,5,6,8]
    #               example-2 - match_index = [0,4,6,4,8] -> sorted -> [0,4,4,6,8]
    #               Now we know that 3 servers (5//2 + 1) must have given the consensus for the commits to happen
    #               Now, the question is which of the 3 servers gave the consensus?
    #                   Since the backtracking began from len(log), you must have received consensus from the servers
    #                   corresponding to the top 3 values in the sorted match_index[] because those 3 indices stopped decrementing sooner than others
    #
    #               Therefore, you select the lowest value of the top (NUM_OF_SERVERS//2 + 1) as the commit index i.e.
    #               for example-1 : new_commit_index = 5
    #               for example-2 : new_commit_index = 4

    new_commit_index = sorted(match_index)[NUM_OF_SERVERS//2 + 1 - 1]
    # +1 to select the mid-point and then -1 to adjust for python 0-based indexing
    if new_commit_index > server.log.last_committed_index:
        server.log.last_committed_index = new_commit_index

    # apply the to-be-applied commands and update the state machine of the follower
    update_state_machine(runtime, server, old_commit_index + 1, new_commit_index)


'''
core backend method -> append entries on the server
'''


def append_entries(runtime, server, leader_prev_index, leader_prev_term, entries_to_be_appended):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(server.log, RaftPersistentLog)

    # print(f'      leader_prev_index={leader_prev_index}, leader_prev_term={leader_prev_term}, log_len={len(server.log.log_entries)}')
    # print("       Entries to be appended => \n   ", entries_to_be_appended)

    # accommodate the initial state when the log is empty and leader_prev_index is at INIT_INDEX(i.e. -1)

    # existing code
    if entries_to_be_appended is None or len(entries_to_be_appended) == 0:
        if leader_prev_index >= len(server.log.log_entries):
            return False, server.log.INIT_INDEX, server.log.INIT_INDEX
        if server.log.log_entries[leader_prev_index].term != leader_prev_term:
            return False, server.log.INIT_INDEX, server.log.INIT_INDEX
        else:
            return True, server.current_term, server.log.INIT_INDEX

    # if server.role == RaftServerRole.LEADER: print('#########################     Stage 1')

    if leader_prev_index != server.log.INIT_INDEX:

        # do not entertain empty request
        if entries_to_be_appended is None:
            return False, server.log.INIT_INDEX, server.log.INIT_INDEX

        # print('#########################     Stage 1.1')

        # gap situation which must be avoided i.e. leader sending entries to be
        # appended at indices which do not even exist in the log
        if leader_prev_index >= len(server.log.log_entries):
            return False, server.log.INIT_INDEX, server.log.INIT_INDEX

        # print('#########################     Stage 1.2')

        # reject the request to append entries, else the continuity is broken
        if server.log.log_entries[leader_prev_index].term != leader_prev_term:
            return False, server.log.INIT_INDEX, server.log.INIT_INDEX

    # if server.role == RaftServerRole.LEADER: print('#########################     Stage 2')

    # AppendEntriesRPC - Receiver implementation - Page 4 of paper
    # start comparing the log entries (from the position after a matching leader_prev_index) with entries to be appended
    log_entries_index = leader_prev_index + 1

    for _, entry in enumerate(entries_to_be_appended):
        assert isinstance(entry, LogEntry)

        # sentinel position - reached the end of the log
        if log_entries_index >= len(server.log.log_entries):
            break

        # no match between entries results in clear the logs (python delete)
        if server.log.log_entries[log_entries_index].term != entry.term:
            # this is for pruning the persistent_log off of entries from non-matching election term
            del server.log.log_entries[log_entries_index:]
            break

    # if server.role == RaftServerRole.LEADER: print('#########################     Stage 3')

    # overwrite every entry to be appended to the log from the position = leader_prev_index + 1
    server.log.log_entries[
    leader_prev_index + 1: leader_prev_index + 1 + len(entries_to_be_appended)] = entries_to_be_appended

    # if server.role == RaftServerRole.LEADER: print(f'#########################     Stage 4 - Core append process successful on {server.id}')

    # return status
    return True, server.current_term, len(server.log.log_entries) - 1


'''
event loop
'''


def kickoff_incoming_messages_event_loop(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    t = threading.Thread(target=incoming_messages_event_loop, args=(runtime, server,))
    t.start()
    print(f'{server.id} -> started Incoming Queue -> Handlers loop')


def incoming_messages_event_loop(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    while True:
        try:
            msg = runtime.incoming_queue.get_nowait()
        except Empty:
            # print(f'    Nothing in the incoming queue of {server.id}')
            continue
        assert isinstance(msg, RaftMessage)

        if isinstance(msg, HeartBeatTick):
            if server.role == RaftServerRole.LEADER:
                handle_heartbeat_tick(runtime, server, msg)

        elif isinstance(msg, ClientAppendRequest):
            if server.role == RaftServerRole.LEADER:
                handle_leader_append_entries(runtime, server, msg)
            else:
                # do not want to lose any client request on the follower or candidate
                # but not sure what to do with this
                # TODO:
                runtime.incoming_queue.put_nowait(msg)

        elif isinstance(msg, AppendEntriesRequest):
            if server.role in {RaftServerRole.FOLLOWER, RaftServerRole.CANDIDATE}:
                # print(f'    Dequed message being processed by {server.id} / {msg.uuid}')

                # Respond to any empty heart beat
                if msg.entries_to_be_appended is None or len(msg.entries_to_be_appended) == 0:
                    # print('Handling empty heart beats at the follower')
                    response_msg = AppendEntriesResponse(follower_current_term=server.current_term,success=True, match_index=server.log.INIT_INDEX,uuid=runtime.gen_uuid(),source=server.id, destination=msg.source,ref_msg_uuid=msg.uuid)
                    runtime.outgoing_queue.put_nowait(response_msg)
                else:
                    handle_append_entries(runtime, server, msg)

        # Want the AppendEntriesResponse to be kind of treated as a synchronous response in the
        # handle_heartbeat_tick() handler. Hence, placing this back in the queue so that leader
        # can call runtime.return_message_from_incoming_queue_with_ref_uuid() and get response
        elif isinstance(msg, AppendEntriesResponse):
            if server.role == RaftServerRole.LEADER:
                runtime.incoming_queue.put_nowait(msg)
                # print(f'     Dequeued {msg} by {server.id}, but placed back on the queue')

        elif isinstance(msg, VoteRequest):
            if server.role == RaftServerRole.FOLLOWER:
                # print(f'    Dequed message being processed by {server.id}')
                grant_vote(runtime, server, msg)

        # Want the VoteResponse to be kind of treated as a synchronous response in the handler
        # Hence, placing this back in the queue so that ,candidate can call
        # runtime.return_message_from_incoming_queue_with_ref_uuid() and get response
        elif isinstance(msg, VoteResponse):
            if server.role == RaftServerRole.CANDIDATE:
                runtime.incoming_queue.put_nowait(msg)
                # print(f'     Dequeued {msg} by {server.id}, but placed back on the queue')

        else:
            pass


def kickoff_network_to_incoming_queue_hydrator(runtime, server):
    t = threading.Thread(target=network_to_incoming_queue_hydrator_wrapper, args=(runtime, server,))
    t.start()


def network_to_incoming_queue_hydrator_wrapper(runtime, server):
    print(f'{server.id} -> started Network -> Incoming Queue loop')
    client_socket = None
    try:
        while True:
            client_socket, client_address = runtime.local_server_conn.accept()
            t = threading.Thread(target=network_to_incoming_queue_hydrator, args=(runtime, server, client_socket,))
            t.start()
    except IOError:
        if client_socket:
            client_socket.close()


def network_to_incoming_queue_hydrator(runtime, server, client_socket):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(client_socket, socket)

    while True:
        try:
            obj = runtime.recv_from_socket(client_socket, runtime.BROADCAST_TIMEOUT)
            if obj:
                runtime.incoming_queue.put_nowait(obj)
                print
                if type(obj) == AppendEntriesRequest:
                    register_leader_last_contact(runtime, server, obj)
                    # print(f'Queue - {runtime.incoming_queue.qsize()} / Resetting the AppendEntries timer on the follower .......... {runtime.last_AppendEntriesRequest_time}')
                # print(f'Received a new message from {obj.source} of type -> {type(obj)}')
        except Exception as e:
            if client_socket:
                client_socket.close()
            print(f'{e} while reading from the network and putting on the input queue')


def kickoff_outgoing_queue_to_network(runtime, server):
    t = threading.Thread(target=outgoing_queue_to_network, args=(runtime, server,))
    t.start()
    print(f'{server.id} -> started Outgoing Queue -> Network loop')


def outgoing_queue_to_network(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    while True:
        obj = None
        try:
            obj = runtime.outgoing_queue.get_nowait()
            assert isinstance(obj, RaftMessage)
        except Empty:
            continue
        if obj:
            assert isinstance(obj, RaftMessage)
            sent_status = runtime.send(obj, obj.destination, runtime.BROADCAST_TIMEOUT)
            # print(f'{obj} wire transfer success status = {sent_status}')
            if not sent_status:
                runtime.outgoing_queue.put_nowait(obj)


'''
leader appending entries
'''


def handle_leader_append_entries(runtime, server, msg):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(server.log, RaftPersistentLog)
    assert isinstance(msg, ClientAppendRequest)

    if len(server.log.log_entries)==0:
        _s, _t, _i = append_entries(runtime, server, leader_prev_index=len(server.log.log_entries) - 1, leader_prev_term=0, entries_to_be_appended=[LogEntry(msg.command, server.current_term, inserted_by=server.id)])
    else:
        leader_prev_term = server.log.log_entries[len(server.log.log_entries) - 1].term
        _s, _t, _i = append_entries(runtime, server, leader_prev_index=len(server.log.log_entries) - 1, leader_prev_term=leader_prev_term, entries_to_be_appended=[LogEntry(msg.command, server.current_term, inserted_by=server.id)])

    if _s:
        server.log.dump()
    else:
        raise RuntimeError(f'Leader {log.server.id} could not append to its own log')


'''
kickoff heartbeat timer
'''


def kickoff_heart_beat_timer(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    t = threading.Thread(target=heart_beat_timer_loop, args=(runtime, server,))
    t.start()
    print(f'{server.id} -> started Heartbeat generation')


def heart_beat_timer_loop(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    while True:
        if server.role == RaftServerRole.LEADER:
            time.sleep(runtime.HEARTBEAT_TIMER)
            msg = HeartBeatTick(runtime.gen_uuid(), server.id, server.id)
            runtime.incoming_queue.put_nowait(msg)


'''
handle heartbeat timer
'''


def handle_heartbeat_tick(runtime, server, msg):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(server.log, RaftPersistentLog)
    assert isinstance(msg, HeartBeatTick)

    # create response_array to track responses from each follower (including self)
    response_array = [False for _ in range(NUM_OF_SERVERS)]
    # leader makes its response to True as it was able to append to its local log (a few steps earlier)
    response_array[server.id.value] = True

    # TODO need to move these two statements to the become_leader code
    server.next_index = [len(server.log.log_entries) for _ in range(NUM_OF_SERVERS)]
    server.match_index = [server.log.INIT_INDEX for _ in range(NUM_OF_SERVERS)]

    # print('response_array initialized -> ', response_array, not all(response_array))
    # print('next_index [] = ', server.next_index)
    # print('match_index [] = ', server.match_index)

    # loop through each not caught up response from followers
    # i = index for each follower in the various arrays and also acts as the key to the _id_to_servers dictionary
    for i, caught_up in enumerate(response_array):

        # In the first run, the server will always be a Leader
        # But upon receiving AppendEntriesResponse from a Follower which is at a term higher than
        # my own current term, I would have become a Follower
        if server.role != RaftServerRole.LEADER:
            break

        # no log replication required for local server
        if _id_to_servers[i] == server.id:
            continue

        # TODO need to make the code multi-threaded so all followers can be called in parallel

        # for each follower that is not caught up
        if not caught_up:

            # start the back track process for the follower
            while True:

                # check if there is anything to backtrack for the follower. If not then break and move to the next follower
                if server.next_index[i] == server.log.INIT_INDEX:
                    break

                # print(f'Attempting backtracked log replication ... from {server.id} to {_id_to_servers[i]} because caught_up_flag = {response_array[i]}')

                server.next_index[i] -= 1

                # from the new next_index, calculate the dependent variables like leader' prev_log_index, leader' prev_log_term
                prev_log_index = server.next_index[i] - 1

                if prev_log_index > server.log.INIT_INDEX:
                    prev_log_term = server.log.log_entries[prev_log_index].term
                else:
                    prev_log_term = 0

                # determine the entries to be sent to the follower
                entries_to_be_appended = server.log.log_entries[server.next_index[i]:]

                # print(f'    leader -> {server.id} / follower -> {_id_to_servers[i]} / to_be_appended -> {entries_to_be_appended}')
                # print(f'    follower prev response={response_array[i]} / next_index={server.next_index[i]} / prev_index = {prev_log_index} / prev_term = {prev_log_term}')

                # package AppendEntriesRequest to be sent to the follower
                request_msg = AppendEntriesRequest(server.current_term, server.id, prev_log_index, prev_log_term,
                                                   entries_to_be_appended, server.log.last_committed_index,
                                                   uuid=runtime.gen_uuid(), source=server.id,
                                                   destination=_id_to_servers[i], ref_msg_uuid=None)

                # print(f'    log -> {server.log.log_entries}')
                # print(f'    Entries to be appended -> {entries_to_be_appended}')

                # send entries to be appended to the follower
                runtime.outgoing_queue.put_nowait(request_msg)

                time.sleep(0.1)

                # wait for response back from the follower
                response_msg = runtime.return_message_from_incoming_queue_with_ref_uuid(message_type=AppendEntriesResponse, uuid_to_check=request_msg.uuid)

                # print(f'    **** **** fetched response from incoming queue -> {response_msg}')

                # response was successful for that follower
                if response_msg:
                    assert isinstance(response_msg, AppendEntriesResponse)
                    if response_msg.success:
                        # update follower' response
                        response_array[i] = True

                        # update match index response from the follower
                        server.match_index[i] = response_msg.match_index

                        # break the loop for the follower as there is no more a need to backtrack
                        break

                    if not response_msg.success and response_msg.follower_current_term > server.current_term:
                        pass
                        # TODO - I should become a follower because my current term as a leader is lower than follower's
                        #become_follower()
                        #break
                else:
                    # got no response for the specific follower
                    break

                # backtrack the next_index for the follower
                server.next_index[i] -= 1

    # check if consensus reached
    if response_array.count(True) > (NUM_OF_SERVERS // 2):
        # print(f'    Consensus reached and ready to commit ...')
        handle_leader_commit_entries(runtime, server, server.match_index)
    else:
        pass
        # print(f'    No consensus reached yet')

    # print(f"The leader {server.id} and all LIVE followers are caught up on the appends")


class VoteRequest(RaftMessage):

    def __init__(self, candidate_id, candidate_term, candidate_last_log_index, candidate_last_log_term, candidate_log_len, uuid, source, destination, ref_msg_uuid=None):
        super().__init__(uuid, source, destination, ref_msg_uuid)
        self.candidate_id = candidate_id
        self.candidate_term = candidate_term
        self.candidate_last_log_index = candidate_last_log_index
        self.candidate_last_log_term = candidate_last_log_term
        self.candidate_log_len = candidate_log_len


    def __repr__(self):
        return f'VoteRequest -> {self.candidate_id} -> {self.destination}  / candidate_term={self.candidate_term} / candidate_last_log_index={self.candidate_last_log_index} / candidate_last_log_term={self.candidate_last_log_term}'

class VoteResponse(RaftMessage):

    def __init__(self, vote_granted, peer_term, uuid, source, destination, ref_msg_uuid=None):
        super().__init__(uuid, source, destination, ref_msg_uuid)
        self.vote_granted = vote_granted
        self.peer_term = peer_term

    def __repr__(self):
        return f'VoteResponse -> vote_granted={self.vote_granted} by {self.source} for {self.destination}/ peer_term={self.peer_term}'


class RaftApplication:
    def __init__(self, state_machine):
        self.state_machine = state_machine

    def apply_to_state_machine(self, command):
        self.state_machine.execute_instruction([command])


class RaftRunTime:
    BROADCAST_TIMEOUT = 0.5
    HEARTBEAT_TIMER = 1
    ELECTION_CHECK_FREQUENCY = 5
    LEADER_CHECKIN_MAX_WAIT = 30

    '''
    To avoid HEARTBEAT_TICKS flooding the 
    '''
    def controlled_put(self, msg, queue, max_count):

        pass

    def __init__(self, application=None):
        self.incoming_queue = Queue()
        self.outgoing_queue = Queue()
        if application:
            assert isinstance(application, RaftApplication)
        self.application = application
        self.local_server_conn = None
        self.remote_server_conns = {}
        # Election timeout related attributes
        self.last_AppendEntriesRequest_time = time.time()
        self.last_AppendEntriesRequest_leader = None
        self.last_AppendEntriesRequest_leader_term = None
        self.voted_for={}
        self.fast_track=True

    def make_follower(self, server):
        assert isinstance(runtime, RaftRunTime)
        assert isinstance(server, RaftServer)
        server.role = RaftServerRole.FOLLOWER
        # print(f'{server.id} became a follower')

    def make_leader(self, server):
        assert isinstance(runtime, RaftRunTime)
        assert isinstance(server, RaftServer)
        server.role = RaftServerRole.LEADER
        print(f'{server.id} became the *** NEW LEADER ***')

        server.next_index = [len(server.log.log_entries) for _ in range(NUM_OF_SERVERS)]
        server.match_index = [server.log.INIT_INDEX for _ in range(NUM_OF_SERVERS)]

        # Generate a no-op ClientAppendRequest. This has the effect of forcing the Leader to do a local commit and
        # issue AppendEntriesRequest -> causing backtracking, validations and handle_append_entries

        request_msg = ClientAppendRequest(command=instructions.NO_OP_COMMAND, uuid=runtime.gen_uuid(), source=server.id,
                                      destination=server.id, ref_msg_uuid=None)

        # Ideally, I would have wanted the NO_OP to get processed in a timely fashion, but it is getting drowned
        # in the tsunami of HEARTBEAT_TICKS. Hence, the queue is being short-circuited.
        # handle_leader_append_entries(self, server, request_msg)
        runtime.incoming_queue.put_nowait(request_msg)

    def role_change_follower_to_candidate(self, server):
        assert isinstance(runtime, RaftRunTime)
        assert isinstance(server, RaftServer)
        server.role = RaftServerRole.CANDIDATE  # promote self to candidate
        server.current_term += 1  # start a new term
        runtime.voted_for[server.current_term] = server.id  # voted for myself for the term
        print(f'{server.id} transitioned to candidate to compete for term={server.current_term} and {self.voted_for}')

    def role_change_candidate_to_follower(self, server):
        assert isinstance(runtime, RaftRunTime)
        assert isinstance(server, RaftServer)
        server.role = RaftServerRole.FOLLOWER  # go back to becoming a follower
        # TODO - should I decrement the term and remove the self vote
        del runtime.voted_for[server.current_term]
        server.current_term -= 1  # go back to original term
        # print(f'{server.id} transitioned from candidate to follower')

    def gen_uuid(self):
        return uuid.uuid4().int

    def object_to_string(self, o):
        return pickle.dumps(o)

    def string_to_object(self, s):
        return pickle.loads(s)

    def send(self, request, server_id, timeout):
        if request is not None and self.remote_server_conns[server_id] is not None:
            try:
                _b = self.object_to_string(request)
                self.remote_server_conns[server_id].settimeout(timeout)
                message.send_message(self.remote_server_conns[server_id], _b)

                return True
            except IOError as e:
                pass
                # print(f'Issues connecting to the remote server {server_id} / {e}')
        return False

    def recv_from_socket(self, client_socket, timeout):
        try:
            _b = message.recv_message(client_socket)
            response = self.string_to_object(_b)
            return response
        except IOError as e:
            pass
            # print(f'Issues receiving objects from the local server {self.local_server_conn} / {e}')
        return None

    # TODO Optimize this function
    def return_message_from_incoming_queue_with_ref_uuid(self, message_type, uuid_to_check):
        start = time.time()
        msg = None
        while True:
            try:
                if time.time() - start > 2:
                    break
                msg = self.incoming_queue.get_nowait()
                if type(msg) == message_type and msg.ref_msg_uuid == uuid_to_check:
                    break
                else:
                    if type(msg) != HeartBeatTick:
                        self.incoming_queue.put_nowait(msg)
            except Empty:
                break
        if type(msg) == message_type:
            return msg
        else:
            return None

    def setup_network_mesh(self, local_server):

        # TODO : put the ability to auto reconnect to restarted servers

        try:
            # bind the server to its listening port
            address_tuple = SERVER_ADDRESSES[server.id]
            server_socket = socket(AF_INET, SOCK_STREAM)
            server_socket.setsockopt(SOL_SOCKET, SO_REUSEADDR, True)
            server_socket.bind(address_tuple)
            server_socket.listen()
            self.local_server_conn = server_socket

            print(f'Server listening @ {address_tuple}')
        except Exception:
            raise RuntimeError(f'Server unable to bind locally at {SERVER_ADDRESSES[server.id]}')

        time.sleep(10)

        # setup connections to peers
        for k1 in _id_to_servers:
            k2 = _id_to_servers[k1]
            if k2 == local_server.id:
                continue
            address_tuple = SERVER_ADDRESSES[k2]
            client_socket = socket(AF_INET, SOCK_STREAM)
            try:
                client_socket.connect(address_tuple)
                print(f'Remote connection established to {k2} {address_tuple}')
                self.remote_server_conns[k2] = client_socket
            except Exception as e:
                print(f'Connection could not be made to {k2} {address_tuple} / {e}')
                self.remote_server_conns[k2] = None


def process_command_line_args(args):
    if len(args) >= 2:
        return int(args[1])
    return None


def test_append_entries(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)
    assert isinstance(server.log, RaftPersistentLog)

    # local leader append first entry
    print('******')
    print(f"0 - scenario: remote leader append")
    server.log.dump()
    log_entries = [LogEntry(command='set x 100', term=1, inserted_by=Servers.Server_1)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=log.INIT_INDEX, leader_prev_term=log.INIT_INDEX,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"1 - scenario: remote leader append")
    server.log.dump()
    log_entries = [LogEntry(command='set y 100', term=2, inserted_by=Servers.Server_1)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=len(server.log.log_entries) - 1, leader_prev_term=1,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"2 - scenario: remote leader append")
    server.log.dump()
    log_entries = [LogEntry(command='set z 100', term=2, inserted_by=Servers.Server_1)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=len(server.log.log_entries) - 1, leader_prev_term=2,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"3 - scenario: remote leader append")
    server.log.dump()
    log_entries = [LogEntry(command='set m 45', term=2, inserted_by=Servers.Server_3)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=len(server.log.log_entries) - 1, leader_prev_term=2,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"4 - scenario: remote leader append - log overwrite scenario")
    server.log.dump()
    log_entries = [
        LogEntry(command='set z 105', term=2, inserted_by=Servers.Server_3),
        LogEntry(command='set m 65', term=2, inserted_by=Servers.Server_3)
    ]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=1, leader_prev_term=2,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"5 - scenario: remote leader append - delayed and shorter message scenario")
    server.log.dump()
    log_entries = [LogEntry(command='set p 25', term=2, inserted_by=Servers.Server_3)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=1, leader_prev_term=2,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"6 - scenario: remote leader append")
    server.log.dump()
    log_entries = [
        LogEntry(command='set d 25', term=2, inserted_by=Servers.Server_3),
        LogEntry(command='set e 25', term=2, inserted_by=Servers.Server_3),
        LogEntry(command='set f 25', term=2, inserted_by=Servers.Server_3)
    ]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=1, leader_prev_term=2,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"7 - scenario: remote leader append - message over-write scenario")
    server.log.dump()
    log_entries = [LogEntry(command='set u 7', term=3, inserted_by=Servers.Server_4)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=0, leader_prev_term=1,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"8 - scenario: remote leader append - message over-write scenario")
    server.log.dump()
    log_entries = [LogEntry(command='set k 43', term=3, inserted_by=Servers.Server_4)]
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=0, leader_prev_term=3,
                                entries_to_be_appended=log_entries)
    server.log.dump()

    # remote leader append entry
    print('******')
    print(f"9 - scenario: remote leader append - empty entries list")
    server.log.dump()
    log_entries = []
    _s, _t, _i = append_entries(runtime, server, leader_prev_index=1, leader_prev_term=3,
                                entries_to_be_appended=log_entries)
    server.log.dump()


def test_handle_heartbeat_ticks_leader(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    runtime.make_leader(server)
    server.current_term=1
    kickoff_heart_beat_timer(runtime, server)
    kickoff_incoming_messages_event_loop(runtime, server)

    print('*** Request - 1 ***')
    r1 = ClientAppendRequest(command='set x 100', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
    runtime.incoming_queue.put_nowait(r1)
    handle_heartbeat_tick(runtime, server, HeartBeatTick(uuid=runtime.gen_uuid(), source=server.id, destination=server.id))
    server.log.dump()

    print('*** Request - 2 ***')
    r2 = ClientAppendRequest(command='set y 100', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
    runtime.incoming_queue.put_nowait(r2)
    handle_heartbeat_tick(runtime, server, HeartBeatTick(uuid=runtime.gen_uuid(), source=server.id, destination=server.id))
    server.log.dump()

    print('*** Request - 3 ***')
    r3 = ClientAppendRequest(command='set d 25', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
    r4 = ClientAppendRequest(command='set e 25', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
    r5 = ClientAppendRequest(command='set f 25', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
    runtime.incoming_queue.put_nowait(r3)
    runtime.incoming_queue.put_nowait(r4)
    runtime.incoming_queue.put_nowait(r5)
    handle_heartbeat_tick(runtime, server,
                          HeartBeatTick(uuid=runtime.gen_uuid(), source=server.id, destination=server.id))
    server.log.dump()


def test_network_transport(runtime, server):
    assert isinstance(runtime, RaftRunTime)
    assert isinstance(server, RaftServer)

    # Server_0 assumes LEADER role
    if server.id == Servers.Server_0:
        runtime.make_leader(server)
        kickoff_outgoing_queue_to_network(runtime, server)
        kickoff_network_to_incoming_queue_hydrator(runtime, server)
        kickoff_incoming_messages_event_loop(runtime, server)
        kickoff_heart_beat_timer(runtime, server)

        print(f'{server.id} becoming the leader')

        r1 = ClientAppendRequest(command='set m -90', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
        r2 = ClientAppendRequest(command='set y 100', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
        r3 = ClientAppendRequest(command='set d 25', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
        r4 = ClientAppendRequest(command='set e 25', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
        r5 = ClientAppendRequest(command='set f 25', uuid=runtime.gen_uuid(), source=server.id, destination=server.id, ref_msg_uuid=None)
        runtime.incoming_queue.put_nowait(r1)
        runtime.incoming_queue.put_nowait(r2)
        runtime.incoming_queue.put_nowait(r3)
        runtime.incoming_queue.put_nowait(r4)
        runtime.incoming_queue.put_nowait(r5)

        print('After putting 5 messages ->', runtime.incoming_queue.qsize(), runtime.incoming_queue.queue)

        # wait for follower to setup
        # time.sleep(10)

        '''
        # 1
        entries_to_be_appended = [LogEntry(command='set x 100', term=1, inserted_by=server.id)]
        request = AppendEntriesRequest(server.current_term, server.id, -1, 0, entries_to_be_appended,
                                       server.log.last_committed_index, uuid=runtime.gen_uuid(), source=server.id,
                                       destination=Servers.Server_1, ref_msg_uuid=None)
        runtime.outgoing_queue.put_nowait(request)

        # 2
        entries_to_be_appended = [LogEntry(command='get x', term=1, inserted_by=server.id),
                                  LogEntry(command='set z 34', term=1, inserted_by=server.id)]
        request = AppendEntriesRequest(1, server.id, 0, 1, entries_to_be_appended,
                                       server.log.last_committed_index, uuid=runtime.gen_uuid(), source=server.id,
                                       destination=Servers.Server_1, ref_msg_uuid=None)
        runtime.outgoing_queue.put_nowait(request)
        '''

    # Server_1 assumes FOLLOWER role
    if server.id == Servers.Server_1 or \
            server.id == Servers.Server_2 or \
            server.id == Servers.Server_3 or \
            server.id == Servers.Server_4:
        runtime.make_follower(server)
        print(f'{server.id} becoming the follower')
        kickoff_incoming_messages_event_loop(runtime, server)
        kickoff_network_to_incoming_queue_hydrator(runtime, server)
        kickoff_outgoing_queue_to_network(runtime, server)
        kickoff_heart_beat_timer(runtime, server)


def test_leader_election(runtime, server):
    runtime.make_follower(server)
    kickoff_incoming_messages_event_loop(runtime, server)
    kickoff_outgoing_queue_to_network(runtime, server)
    kickoff_network_to_incoming_queue_hydrator(runtime, server)
    kickoff_election_timeout_checker(runtime, server)
    kickoff_heart_beat_timer(runtime, server)


if __name__ == '__main__':
    _id = process_command_line_args(sys.argv)
    server_id = _id_to_servers[_id]
    if server_id:
        server = RaftServer(server_id)
        log = RaftPersistentLog(server)
        runtime = RaftRunTime()
        runtime.setup_network_mesh(server)
        test_leader_election(runtime, server)
        # test_network_transport(runtime, server)
        # test_handle_heartbeat_ticks_leader(runtime, server)

    else:
        print(f'Provide number of the server to start. Example: $ python raft 0')
