# This file is Copyright (c) 2019 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

from migen import *

from migen.genlib.misc import WaitTimer

# Note: Currently just FSM skeletons with states/transitions.

# Link Training and Status State Machine -----------------------------------------------------------

@ResetInserter()
class LTSSMFSM(FSM):
    """Link Training and Status State Machine (section 7.5)"""
    def __init__(self):
        # FSM --------------------------------------------------------------------------------------
        FSM.__init__(self, reset_state="SS-INACTIVE")

        # SSInactive State -------------------------------------------------------------------------
        self.act("SS-INACTIVE",
            NextState("RX-DETECT"), # Warm reset, far-end termination absent.
        )

        # SSDisabled State -------------------------------------------------------------------------
        self.act("SS-DISABLED",
            NextState("RX-DETECT"), # Directed, PowerOn reset, USB2 bus reset
        )

        # RXDetect State ---------------------------------------------------------------------------
        self.act("RX-DETECT",
            NextState("SS-DISABLED"), # RXDetect events over limit (Dev) or directed (DS).
        )

        # Polling State ----------------------------------------------------------------------------
        self.act("POLLING",
            NextState("U0"),               # Idle symbol handshake.
            NextState("HOT-RESET"),        # Directed.
            NextState("LOOPBACK"),         # Directed.
            NextState("COMPLIANCE-MODE"),  # First LFPS timeout.
            NextState("SS-DISABLED"),       # Timeout, directed
        )

        # U0 State ---------------------------------------------------------------------------------
        self.act("U0",
            NextState("U1"),       # LGO_U1
            NextState("U2"),       # LGO_U2
            NextState("U3"),       # LGO_U3
            NextState("RECOVERY"), # Error, directed.
        )

        # U1 State ---------------------------------------------------------------------------------
        self.act("U1",
            NextState("U2"),          # Timeout.
            NextState("SS-INACTIVE"), # LFPS timeout.
        )

        # U2 State ---------------------------------------------------------------------------------
        self.act("U2",
            NextState("SS-INACTIVE"), # LFPS timeout.
            NextState("RECOVERY"),    # LTPS handshake.
        )

        # U3 State ---------------------------------------------------------------------------------
        self.act("U3",
            NextState("RECOVERY"), # LTPS handshake.
        )

        # Compliance Mode State --------------------------------------------------------------------
        self.act("COMPLIANCE-MODE",
            NextState("RX-DETECT"),  # Warm reset, PowerOn reset.
        )

        # Loopback State ---------------------------------------------------------------------------
        self.act("LOOPBACK",
            NextState("SS-INACTIVE"), # Timeout.
            NextState("RX-DETECT"),   # LFPS handshake.
        )

        # Hot Reset State --------------------------------------------------------------------------
        self.act("HOT-RESET",
            NextState("SS-INACTIVE"), # Timeout.
            NextState("U0"),          # Idle symbol handshake.
        )

        # Recovery ---------------------------------------------------------------------------------
        self.act("RECOVERY",
            NextState("U0"),          # Training.
            NextState("HOT-RESET"),   # Directed.
            NextState("SS-INACTIVE"), # Timeout.
            NextState("LOOPBACK"),    # Directed.
        )

        # End State --------------------------------------------------------------------------------
        self.act("END")

# SSInactive Finite State Machine  -----------------------------------------------------------------

@ResetInserter()
class SSInactiveFSM(FSM):
    """SSInactive Finite State Machine (section 7.5.2)"""
    def __init__(self):
        self.exit_to_ss_disabled = Signal()
        self.exit_to_rx_detect   = Signal()

        # FSM --------------------------------------------------------------------------------------
        FSM.__init__(self, reset_state="QUIET")

        # QUIET State ------------------------------------------------------------------------------
        self.act("QUIET",
            NextState("DETECT"),             # Timeout
            self.exit_to_ss_disabled.eq(1),  # Directed (DS).
            self.exit_to_rx_detect.eq(1),    # Warm reset.
            NextState("END"),                # On any exit case.
        )

        # DETECT State -----------------------------------------------------------------------------
        self.act("DETECT",
            NextState("QUIET"),              # Far-end termination present.
            self.exit_to_rx_detect.eq(1),    # Far-end termination absent.
            NextState("END"),                # On any exit case.
        )

        # End State --------------------------------------------------------------------------------
        self.act("END")

# RXDetect Finite State Machine  -------------------------------------------------------------------

@ResetInserter()
class RXDetectFSM(FSM):
    """RxDetect Finite State Machine (section 7.5.3)"""
    def __init__(self):
        self.exit_to_ss_disabled = Signal()
        self.exit_to_polling     = Signal()

        # FSM --------------------------------------------------------------------------------------
        FSM.__init__(self, reset_state="RESET")

        # Reset State ------------------------------------------------------------------------------
        self.act("RESET",
            NextState("ACTIVE"),             # Warm reset de-asserted.
            self.exit_to_ss_disabled.eq(1),  # Directed (DS).
            NextState("END"),                # On any exit case.
        )

        # Detect State -----------------------------------------------------------------------------
        self.act("ACTIVE",
            NextState("QUIET"),              # Far-end termination not detected.
            self.exit_to_polling.eq(1),      # Far-end termination detected.
            self.exit_to_ss_disabled.eq(1),  # RXDetect events over limit (Dev) or directed (DS).
            NextState("END"),                # On any exit case.
        )

        # Quiet State ------------------------------------------------------------------------------
        self.act("QUIET",
            NextState("ACTIVE"),             # Timeout.
            self.exit_to_ss_disabled.eq(1),  # Directed (DS).
            NextState("END"),                # On any exit case.
        )

        # End State --------------------------------------------------------------------------------
        self.act("END")

# Polling Finite State Machine  --------------------------------------------------------------------

@ResetInserter()
class PollingFSM(FSM):
    """ Polling Finite State Machine (section 7.5.4)"""
    def __init__(self, serdes, lfps_unit, ts_unit):
        self.exit_to_compliance_mode = Signal()
        self.exit_to_rx_detect       = Signal()
        self.exit_to_ss_disabled     = Signal()
        self.exit_to_loopback        = Signal()
        self.exit_to_hot_reset       = Signal()
        self.exit_to_u0              = Signal()
        self.idle                    = Signal()

        # # #

        # FSM --------------------------------------------------------------------------------------
        FSM.__init__(self, reset_state="LFPS")

        # LFPS State -------------------------------------------------------------------------------
        self.act("LFPS",
            serdes.rx_align.eq(1),
            lfps_unit.tx_polling.eq(1),
            If(lfps_unit.rx_polling,
                NextState("RX-EQ"),                  # LFPS handshake.
            ),
            #self.exit_to_compliance_mode.eq(1),     # First LFPS timeout.
            #self.exit_to_ss_disabled.eq(1),         # Subsequent LFPS timeouts (Dev) or directed (DS).
            #self.exit_to_rx_detect.eq(1),           # Subsequent LFPS timeouts (DS).
            #NextState("END"),                       # On any exit case.
        )

        # RxEQ State -------------------------------------------------------------------------------
        self.act("RX-EQ",
            serdes.rx_align.eq(1),
            lfps_unit.tx_polling.eq(1),
            ts_unit.rx_enable.eq(1),
            If(ts_unit.rx_tseq,
                NextState("ACTIVE"),                # TSEQ transmitted.
            ),
            #self.exit_to_ss_disabled.eq(1),        # Directed (DS).
            #NextState("END"),                      # On any exit case.
        )

        # Active State -----------------------------------------------------------------------------
        self.act("ACTIVE",
            ts_unit.rx_enable.eq(1),
            If(ts_unit.rx_ts1 | ts_unit.rx_ts2,
                NextState("CONFIGURATION"),         # 8 consecutiive TS1 or TS2 received.
            ),
            #self.exit_to_ss_disabled.eq(1),        # Timeout (Dev) or directed (DS).
            #self.exit_to_rx_detect.eq(1),          # Timeout (DS).
            #NextState("END")                       # On any exit case.
        )

        # Configuration State ----------------------------------------------------------------------
        self.act("CONFIGURATION",
            ts_unit.rx_enable.eq(1),
            ts_unit.tx_enable.eq(1),
            ts_unit.tx_ts2.eq(1),
            If(ts_unit.rx_ts2,
                NextState("IDLE"),                  # TS2 handshake.
            ),
            #self.exit_to_ss_disabled.eq(1),        # Timeout (Dev) or directed (DS).
            #self.exit_to_rx_detect.eq(1),          # Timeout (DS).
            #NextState("END"),                      # On any exit case.
        )

        # Idle State -------------------------------------------------------------------------------
        self.act("IDLE",
            self.idle.eq(1),
            #self.exit_to_ss_disabled.eq(1),     # Timeout (Dev) or directed (DS).
            #self.exit_to_rx_detect.eq(1),       # Timeout (DS).
            #self.exit_to_loopback.eq(1),        # Directed.
            #self.exit_to_hot_reset.eq(1),       # Directed.
            #self.exit_to_u0.eq(1),              # Idle symbol handshake.
            #NextState("END"),                   # On any exit case.
        )

        # End State --------------------------------------------------------------------------------
        self.act("END")

# Link Training and Status State Machine -----------------------------------------------------------

class LTSSM(Module):
    def __init__(self, serdes, lfps_unit, ts_unit, sys_clk_freq):
        # SS Inactive FSM --------------------------------------------------------------------------
        self.submodules.ss_inactive_fsm = SSInactiveFSM()

        # RX Detect FSM ----------------------------------------------------------------------------
        self.submodules.rx_detect_fsm   = RXDetectFSM()

        # Polling FSM ------------------------------------------------------------------------------
        self.submodules.polling_fsm     = PollingFSM(
            serdes    = serdes,
            lfps_unit = lfps_unit,
            ts_unit   = ts_unit)

        # LTSSM FSM --------------------------------------------------------------------------------
        self.submodules.ltssm_fsm       = LTSSMFSM()

        # FIXME; Experimental RX polarity swap
        rx_polarity_timer = WaitTimer(int(sys_clk_freq*1e-3))
        self.submodules += rx_polarity_timer
        self.comb += rx_polarity_timer.wait.eq(self.polling_fsm.ongoing("RX-EQ") & ~rx_polarity_timer.done)
        self.sync += If(rx_polarity_timer.done, serdes.rx_polarity.eq(~serdes.rx_polarity))
