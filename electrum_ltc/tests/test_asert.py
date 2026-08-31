"""Tests for the ASERT difficulty algorithm and the difficulty-reset fork.

These mirror the ASERT cases in the node's src/test/pow_tests.cpp. The client
re-implements the consensus rule, so the two have to agree exactly or the
wallet stops syncing.
"""

from electrum_ltc import constants
from electrum_ltc.blockchain import Blockchain, MAX_TARGET

from . import ElectrumTestCase


def _header(height, timestamp, bits):
    return {'block_height': height, 'timestamp': timestamp, 'bits': bits}


class _FakeChain(Blockchain):
    """A Blockchain that reads headers from a dict instead of a headers file.

    Deliberately does not call Blockchain.__init__: the difficulty code only
    ever reaches the chain through _get_header_by_height.
    """

    def __init__(self, headers):
        self._headers = {h['block_height']: h for h in headers}

    def _get_header_by_height(self, height, recent_headers=None):
        return self._headers.get(height)


class TestASERT(ElectrumTestCase):

    def setUp(self):
        super().setUp()
        self.net = constants.net
        self.anchor2_target = Blockchain.bits_to_target(self.net.ASERT2_ANCHOR_BITS)
        # powLimit as the client can express it: MAX_TARGET has more
        # significant bits than nBits' 24-bit mantissa, so the round trip is
        # lossy and comparisons have to be made in compact form.
        self.pow_limit = Blockchain.bits_to_target(Blockchain.target_to_bits(MAX_TARGET))

    def test_params_match_the_node(self):
        # If these drift from chainparams.cpp everything below is meaningless.
        self.assertEqual(1246000, self.net.ASERT_HEIGHT)
        self.assertEqual(0x1d18ffe7, self.net.ASERT_ANCHOR_BITS)
        self.assertEqual(3600, self.net.ASERT_HALF_LIFE)
        self.assertEqual(1359052, self.net.ASERT2_HEIGHT)
        self.assertEqual(0x1d027ffd, self.net.ASERT2_ANCHOR_BITS)

    def test_fork_block_uses_fixed_anchor_bits(self):
        """The fork block is the anchor, so it cannot be derived from one."""
        chain = _FakeChain([
            _header(1245999, 1769808705, 0x1d18ffe7),
            _header(1359051, 1787340378, 0x1b49d9c4),
        ])
        target = chain.get_target_for_block(self.net.ASERT2_HEIGHT)
        self.assertEqual(self.net.ASERT2_ANCHOR_BITS, Blockchain.target_to_bits(target))

    def test_stalled_tip_would_otherwise_be_powlimit(self):
        """Regression for the reason this fork exists.

        Against the original anchor the real stalled tip is 6.64 days behind
        schedule, so anchor-1 ASERT clamps to powLimit. The chain requires
        0x1d027ffd there instead, and a client without the re-anchor rejects
        block 1359052 with a bits mismatch and never syncs past 1359051.
        """
        chain = _FakeChain([
            _header(1245999, 1769808705, 0x1d18ffe7),
            _header(1359051, 1787340378, 0x1b49d9c4),
        ])
        stale = chain._get_target_asert(self.net.ASERT2_HEIGHT)
        self.assertEqual(0x1e0fffff, Blockchain.target_to_bits(stale))
        self.assertNotEqual(
            Blockchain.target_to_bits(stale),
            Blockchain.target_to_bits(chain.get_target_for_block(self.net.ASERT2_HEIGHT)))

    def test_reset_does_not_inherit_stall_debt(self):
        """However long the pre-anchor gap was, the fork starts at zero debt.

        The new schedule's origin is the anchor's own timestamp, so the first
        block after it sees a deviation of exactly zero and is mined at the
        anchor difficulty -- not at powLimit followed by a catch-up burst.
        """
        stalled_time = 1787340378
        for gap_days in (6, 60):
            anchor_time = stalled_time + gap_days * 24 * 3600
            chain = _FakeChain([
                _header(1359051, stalled_time, 0x1b49d9c4),
                _header(self.net.ASERT2_HEIGHT, anchor_time, self.net.ASERT2_ANCHOR_BITS),
            ])
            target = chain.get_target_for_block(self.net.ASERT2_HEIGHT + 1)
            self.assertEqual(self.net.ASERT2_ANCHOR_BITS, Blockchain.target_to_bits(target),
                             msg=f"gap of {gap_days} days did not reset cleanly")
            # Explicitly: it must not have collapsed to powLimit, which is what
            # inheriting the debt would have produced.
            self.assertNotEqual(Blockchain.target_to_bits(self.pow_limit),
                                Blockchain.target_to_bits(target))

    def test_does_not_rewrite_history(self):
        """Every height at or below the fork still routes to the first anchor,
        so blocks 1246001-1359051 validate bit-for-bit as they always did."""
        anchor_parent_time = 1769808705
        headers = [_header(self.net.ASERT_HEIGHT - 1, anchor_parent_time, 0x1d18ffe7)]
        height = self.net.ASERT_HEIGHT + 30
        headers.append(_header(height - 1, anchor_parent_time + 30 * 140, 0x1d18ffe7))
        chain = _FakeChain(headers)

        via_dispatch = chain.get_target_for_block(height)
        via_anchor1 = chain._get_target_asert(height)

        self.assertEqual(via_anchor1, via_dispatch)
        self.assertNotEqual(self.net.ASERT2_ANCHOR_BITS, Blockchain.target_to_bits(via_dispatch))

    def test_retargets_in_the_right_direction(self):
        T = self.net.POW_TARGET_SPACING
        anchor_time = 1787860000

        def next_target_with_drift(drift):
            chain = _FakeChain([
                _header(self.net.ASERT2_HEIGHT, anchor_time, self.net.ASERT2_ANCHOR_BITS),
                _header(self.net.ASERT2_HEIGHT + 1, anchor_time + T + drift,
                        self.net.ASERT2_ANCHOR_BITS),
            ])
            return chain.get_target_for_block(self.net.ASERT2_HEIGHT + 2)

        on_schedule = next_target_with_drift(0)
        self.assertEqual(self.net.ASERT2_ANCHOR_BITS, Blockchain.target_to_bits(on_schedule))

        # Behind schedule -> easier (bigger target); ahead -> harder.
        self.assertGreater(next_target_with_drift(3600), on_schedule)
        self.assertLess(next_target_with_drift(-100), on_schedule)

        # One halflife behind roughly halves the difficulty (doubles the target).
        one_halflife_late = next_target_with_drift(self.net.ASERT_HALF_LIFE)
        self.assertGreater(one_halflife_late, on_schedule * 19 // 10)
        self.assertLess(one_halflife_late, on_schedule * 21 // 10)

        # A 30-day post-fork stall must clamp to powLimit, never invert to 1.
        long_stall = next_target_with_drift(30 * 24 * 3600)
        self.assertEqual(Blockchain.target_to_bits(self.pow_limit),
                         Blockchain.target_to_bits(long_stall))
        self.assertGreater(long_stall, 1)

    def test_lateness_never_inverts_the_target(self):
        """Sweep 0-40 days of lateness. This is where the node overflowed:
        arith_uint256's <<= dropped every bit past 255 and wrapped the target
        to 1. Python ints cannot, but the clamp still has to hold."""
        T = self.net.POW_TARGET_SPACING
        anchor_time = 1787860000
        for days in range(0, 41):
            chain = _FakeChain([
                _header(self.net.ASERT2_HEIGHT, anchor_time, self.net.ASERT2_ANCHOR_BITS),
                _header(self.net.ASERT2_HEIGHT + 1,
                        anchor_time + T + days * 24 * 3600, self.net.ASERT2_ANCHOR_BITS),
            ])
            target = chain.get_target_for_block(self.net.ASERT2_HEIGHT + 2)
            self.assertGreaterEqual(target, self.anchor2_target,
                                    msg=f"{days} days late made the target harder")
            self.assertLessEqual(target, self.pow_limit,
                                 msg=f"{days} days late exceeded powLimit")
