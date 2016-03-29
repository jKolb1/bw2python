import contextlib
import random

def _validate_payload_type_num(type_num):
    return 0 <= type_num

def _validate_payload_type_dotted(type_dotted):
    return len(type_dotted) == 4 and all([0 <= x < 255 for x in type_dotted])

def _validate_payload_type_both(type_dotted, type_num):
    octet_val = (type_dotted[0] << 24) + (type_dotted[1] << 16) + (type_dotted[2] << 8) + type_dotted[3]
    return octet_val == type_num

class RoutingObject(object):
    def __init__(self, number, content):
        if number < 0 or number > 255:
            raise ValueError("Routing object number must be between 0 and 255")
        self.number = number
        self.content = content

class PayloadObject(object):
    def __init__(self, type_dotted, type_num, content):
        if type_dotted is None and type_num is None:
            raise ValueError("Failed to specify payload object type")
        self.type_dotted = None
        self.type_num = None

        if type_dotted is not None:
            if not _validate_payload_type_dotted(type_dotted):
                raise ValueError("Invalid dotted payload object type")
            self.type_dotted = type_dotted
        if type_num is not None:
            if not _validate_payload_type_num(type_num):
                raise ValueError("Invalid payload object type number")
            self.type_num = type_num
        if self.type_dotted is not None and self.type_num is not None:
            if not _validate_payload_type_both(self.type_dotted, self.type_num):
                raise ValueError("Payload object type octet and number don't agree")

        self.content = content

class Frame(object):
    def __init__(self, command, seq_num):
        self.command = command
        self.seq_num = seq_num
        self.kv_pairs = []
        self.routing_objects = []
        self.payload_objects = []

    def addKVPair(self, key, value):
        self.kv_pairs.append((key, value))

    def addRoutingObject(self, ro):
        self.routing_objects.append(ro)

    def addPayloadObject(self, po):
        self.payload_objects.append(po)

    def getFirstValue(self, key):
        matchingValues = [y for x,y in self.kv_pairs if x == key]
        if len(matchingValues) > 0:
            return matchingValues[0]
        else:
            return None

    def writeToSocket(self, sock):
        body = "{0} 0000000000 {1:010d}\n".format(self.command, self.seq_num)
        for (key, value) in self.kv_pairs:
            body += "kv {0} {1}\n".format(key, len(value))
            body += value + "\n"

        for ro in self.routing_objects:
            body += "ro {0} {1}\n".format(ro.number, len(ro.content))
            body += ro.content + "\n"

        for po in self.payload_objects:
            type_str = ""
            if po.type_dotted is not None:
                type_str += "{0}.{1}.{2}.{3}".format(*po.type_dotted)
            type_str += ":"
            if po.type_num is not None:
                type_str += str(po.type_num)

            body += "po {0} {1}\n".format(type_str, len(po.content))
            body += po.content + "\n"

        body += "end\n"
        sock.sendall(body)

    @classmethod
    def readFromSocket(cls, socket):
        with contextlib.closing(socket.makefile()) as f:
            frame_header = f.readline()
            header_items = frame_header.split(' ')
            if len(header_items) != 3:
                raise ValueError("Frame header must contain 3 fields")

            command = header_items[0]
            frame_length = int(header_items[1])
            if frame_length < 0:
                raise ValueError("Negative frame length")
            seq_no = int(header_items[2])
            frame = cls(command, seq_no)

            current_line = f.readline().strip()
            while current_line != 'end':
                fields = current_line.split(' ')
                if len(fields) != 3:
                    raise ValueError("Invalid item header: " + current_line)

                if fields[0] == "kv":
                    key = fields[1]
                    value_len = int(fields[2])

                    value = f.read(value_len)
                    frame.addKVPair(key, value)
                    f.read(1) # Strip trailing \n

                elif fields[0] == "ro":
                    ro_num = int(fields[1])
                    body_len = int(fields[2])
                    body = f.read(body_len)
                    ro = RoutingObject(ro_num, value)
                    frame.addRoutingObject(ro)
                    f.read(1) # Strip trailing \n

                elif fields[0] == "po":
                    body_len = int(fields[2])
                    body = f.read(body_len)

                    po_type = fields[1]
                    if ':' not in po_type:
                        raise ValueError("Inavlid payload object type: " + po_type)
                    if po_type.startswith(':'):
                        po_type_num = int(po_type[1:])
                        po_type_dotted = None
                    elif po_type.endswith(':'):
                        po_type_dotted = tuple([int(x) for x in po_type[:-1].split('.')])
                        po_type_num = None
                    else:
                        type_tokens = po_type.split(':')
                        if len(type_tokens) != 2:
                            raise ValueError("Invalid payload object type: " + po_type)
                        po_type_dotted = tuple([int(x) for x in type_tokens[0].split('.')])
                        po_type_num = int(type_tokens[1])

                    po = PayloadObject(po_type_dotted, po_type_num, body)
                    frame.addPayloadObject(po)
                    f.read(1) # Strip trailing \n

                else:
                    raise ValueError("Invalid item header: " + current_line)

                current_line = f.readline().strip()
        return frame

    @staticmethod
    def generateSequenceNumber():
        return random.randint(0, 2**32 - 1)

class BosswaveResponse(object):
    def __init__(self, status, reason):
        self.status = status
        self.reason = reason

class BosswaveResult(object):
    def __init__(self, from_, uri, routing_objects, payload_objects):
        self.from_ = from_
        self.uri = uri
        self.routing_objects = routing_objects
        self.payload_objects = payload_objects
