"""End-to-end on loopback: a fake phone calls the server, which echoes audio."""
import array
import asyncio
import socket
import struct
import unittest

from agent_sip.config import SipConfig
from agent_sip.sip import Call, CallHandler, SipServer
from agent_sip.sip import g711
from agent_sip.sip.message import parse
from agent_sip.sip.sdp import parse_rtp_target


class Echo(CallHandler):
    def __init__(self):
        self.ended = asyncio.Event()

    async def on_call(self, call: Call) -> None:
        await call.play(array.array("h", [1000] * 800))   # 100 ms

    async def on_call_end(self, call: Call) -> None:
        self.ended.set()


class Flow(unittest.IsolatedAsyncioTestCase):
    async def test_incoming_call(self):
        cfg = SipConfig(local_ip="127.0.0.1", bind_host="127.0.0.1", port=55060,
                        rtp_port_min=55100, rtp_port_max=55120)
        handler = Echo()
        server = SipServer(cfg, handler)
        await server.start()
        phone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        phone.bind(("127.0.0.1", 0))
        phone.setblocking(False)
        loop = asyncio.get_running_loop()
        rtp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rtp.bind(("127.0.0.1", 0))
        rtp.setblocking(False)
        sdp = ("v=0\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\n"
               f"m=audio {rtp.getsockname()[1]} RTP/AVP 0\r\n")
        port = phone.getsockname()[1]
        invite = (f"INVITE sip:100@127.0.0.1 SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1:{port};branch=z9hG4bKx\r\n"
                  f"From: <sip:p@127.0.0.1>;tag=a\r\nTo: <sip:100@127.0.0.1>\r\nCall-ID: c1\r\n"
                  f"CSeq: 1 INVITE\r\nContact: <sip:p@127.0.0.1:{port}>\r\n"
                  f"Content-Length: {len(sdp)}\r\n\r\n{sdp}")
        phone.sendto(invite.encode(), ("127.0.0.1", 55060))

        codes, ok = [], None
        while ok is None:
            data = await asyncio.wait_for(loop.sock_recv(phone, 4096), 2)
            m = parse(data)
            codes.append(m.status)
            if m.status == 200:
                ok = m
        self.assertEqual(codes, [180, 200])
        remote = parse_rtp_target(ok.body)
        phone.sendto(b"ACK sip:agent@127.0.0.1:55060 SIP/2.0\r\nCall-ID: c1\r\nCSeq: 1 ACK\r\n"
                     b"Content-Length: 0\r\n\r\n", ("127.0.0.1", 55060))

        # send some RTP, expect RTP back
        rtp.sendto(struct.pack("!BBHII", 0x80, 0, 1, 0, 1) + g711.encode([0] * 160), remote)
        pkt = await asyncio.wait_for(loop.sock_recv(rtp, 4096), 2)
        self.assertEqual(len(pkt), 12 + 160)

        # handler finishes -> server sends BYE
        while True:
            data = await asyncio.wait_for(loop.sock_recv(phone, 4096), 2)
            m = parse(data)
            if not m.is_response and m.method == "BYE":
                break
        await asyncio.wait_for(handler.ended.wait(), 2)
        self.assertEqual(server.calls, {})
        await server.stop()
        phone.close()
        rtp.close()

    async def test_lost_200_is_retransmitted_then_hangup(self):
        cfg = SipConfig(local_ip="127.0.0.1", bind_host="127.0.0.1", port=55061,
                        rtp_port_min=55130, rtp_port_max=55150)
        handler = Echo()
        server = SipServer(cfg, handler)
        await server.start()
        phone = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        phone.bind(("127.0.0.1", 0))
        phone.setblocking(False)
        loop = asyncio.get_running_loop()
        sdp = "v=0\r\nc=IN IP4 127.0.0.1\r\nt=0 0\r\nm=audio 55199 RTP/AVP 0\r\n"
        port = phone.getsockname()[1]
        invite = (f"INVITE sip:100@127.0.0.1 SIP/2.0\r\nVia: SIP/2.0/UDP 127.0.0.1:{port};branch=z9hG4bKy\r\n"
                  f"From: <sip:p@127.0.0.1>;tag=a\r\nTo: <sip:100@127.0.0.1>\r\nCall-ID: c2\r\n"
                  f"CSeq: 1 INVITE\r\nContact: <sip:p@127.0.0.1:{port}>\r\n"
                  f"Content-Length: {len(sdp)}\r\n\r\n{sdp}")
        phone.sendto(invite.encode(), ("127.0.0.1", 55061))
        got_200 = 0
        while got_200 < 2:          # pretend the first 200 was lost: never ACK, expect a resend
            m = parse(await asyncio.wait_for(loop.sock_recv(phone, 4096), 3))
            got_200 += m.status == 200
        self.assertIn("c2", server.calls)
        phone.sendto(b"ACK sip:agent@127.0.0.1:55061 SIP/2.0\r\nCall-ID: c2\r\nCSeq: 1 ACK\r\n"
                     b"Content-Length: 0\r\n\r\n", ("127.0.0.1", 55061))
        await asyncio.wait_for(handler.ended.wait(), 3)
        await server.stop()
        phone.close()


if __name__ == "__main__":
    unittest.main()
