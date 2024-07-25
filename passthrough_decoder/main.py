import time
import threading
import tomllib
import pylsl

import numpy as np
from scipy.signal import decimate
from fire import Fire
from dareplane_utils.stream_watcher.lsl_stream_watcher import (
    StreamWatcher,
    pylsl_xmlelement_to_dict,
)

from dareplane_utils.general.ringbuffer import RingBuffer
from dareplane_utils.general.time import sleep_s

from passthrough_decoder.utils.logging import logger
from passthrough_decoder.utils.time import sleep_s


# Start counting at 1
CHANNEL_TO_PASS = 3


def init_lsl_outlet(cfg: dict) -> pylsl.StreamOutlet:
    n_channels = 1
    info = pylsl.StreamInfo(
        cfg["lsl_outlet"]["name"],
        cfg["lsl_outlet"]["type"],
        n_channels,
        cfg["lsl_outlet"]["nominal_freq_hz"],
        cfg["lsl_outlet"]["format"],
    )

    # enrich a channel name
    chns = info.desc().append_child("channels")
    ch = chns.append_child("channel")
    ch.append_child_value("label", "passthrough_decoding")
    ch.append_child_value("unit", "AU")
    ch.append_child_value("type", "decoding_pipeline_prediction")
    ch.append_child_value("scaling_factor", "1")

    outlet = pylsl.StreamOutlet(info)

    return outlet


def connect_stream_watcher(config: dict) -> StreamWatcher:
    """Connect the stream watchers"""
    sw = StreamWatcher(
        config["stream_to_query"]["stream"],
        buffer_size_s=config["stream_to_query"]["buffer_size_s"],
    )
    sw.connect_to_stream()

    # If we connect to the AOStream, we need to hand-tune the buffer, as the
    # provided sfreq in the LSL info is false.
    n_samples = int(config["stream_to_query"]["buffer_size_s"] * 22_000)
    sw.ring_buffer = RingBuffer((n_samples, len(sw.channel_names)))
    sw.buffer = sw.ring_buffer.buffer
    sw.buffer_t = sw.ring_buffer.buffer_t
    sw.last_t = sw.ring_buffer.last_t
    sw.curr_i = sw.ring_buffer.curr_i

    # if the outlet config is to be derived, calc from here
    if config["lsl_outlet"]["nominal_freq_hz"] == "derive":
        inlet_info = pylsl_xmlelement_to_dict(sw.inlet.info())
        config["lsl_outlet"]["nominal_freq_hz"] = float(
            inlet_info["info"]["nominal_srate"]
        )

    return sw


def main(
    stop_event: threading.Event = threading.Event(), logger_level: int = 10
):
    logger.setLevel(logger_level)
    config = tomllib.load(open("./configs/passthrough_config.toml", "rb"))
    derived = (
        True if config["lsl_outlet"]["nominal_freq_hz"] == "derive" else False
    )
    sw = connect_stream_watcher(config)

    logger.debug("StreamWatcher is connected")
    outlet = init_lsl_outlet(config)

    tlast = pylsl.local_clock()
    tstart = time.time_ns()

    # Two while stages for performance
    logger.debug("Starting passthrough loop")

    # do the initial delay separately
    while (
        time.time_ns() - tstart
        < config["lsl_outlet"]["initial_delay_s"] * 10**9
    ):
        sleep_s(config["lsl_outlet"]["initial_delay_s"] * 0.5)
    logger.debug(f"Initial delay of {config["lsl_outlet"]["initial_delay_s"]=}")

    stop_event.clear()

    # Always use the derived loop version for the 
    derived_loop(sw, config, stop_event, outlet)


def derived_loop(
    sw: StreamWatcher,
    config: dict,
    stop_event: threading.Event,
    outlet: pylsl.StreamOutlet,
):
    """Loop for pushing data with derived nominal_freq_hz"""

    tlast = pylsl.local_clock()

    while not stop_event.is_set():
        sw.update()
        req_samples = int(
            config["lsl_outlet"]["nominal_freq_hz"]
            * (pylsl.local_clock() - tlast)
        )

        # This is only correct if the nominal_freq_hz is derived from the source stream
        if req_samples > 0 and sw.n_new > 0:
            # print(f"Pushing: {req_samples=}, from {sw.n_new=}")
            # logger.debug(f"Pushing: {sw.unfold_buffer()[-sw.n_new:, CHANNEL_TO_PASS -1]}")
            tlast = pylsl.local_clock()

            # push rectified version of data for the AO experiment as we need to limit CPU load for fair benchmarking
            # for s in sw.unfold_buffer()[-sw.n_new :, CHANNEL_TO_PASS - 1]:
            med = np.median(sw.unfold_buffer()[-sw.n_new :, CHANNEL_TO_PASS - 1])
            for s in range(req_samples):
                outlet.push_sample([med])
            sw.n_new = 0

            dsleep = 0.95 / config["lsl_outlet"]["nominal_freq_hz"]
            sleep_s(dsleep)


def nominal_srate_loop(
    sw: StreamWatcher,
    config: dict,
    stop_event: threading.Event,
    outlet: pylsl.StreamOutlet,
):
    """Loop for pushing data with provided nominal_freq_hz"""

    srate = config["lsl_outlet"]["nominal_freq_hz"]

    tlast = pylsl.local_clock()

    while not stop_event.is_set():
        sw.update()

        # this is the number of samples that should be passed on
        req_samples = int(srate * (pylsl.local_clock() - tlast))

        # This is only correct if the nominal_freq_hz is derived from the source stream
        if (
            req_samples > 0 and sw.n_new > req_samples
        ):  # Note here we also skip if there is not enoug data from the inlet
            chunk = sw.unfold_buffer()[-sw.n_new :, CHANNEL_TO_PASS - 1]
            # print(f"{sw.n_new=}")
            # print(f"{req_samples=}")
            q = np.floor(sw.n_new / req_samples).astype(int)

            if q > 1:
                logger.debug(f"Decimating with {q=}")
                chunk_d = decimate(chunk, q, ftype="fir")
                outlet.push_chunk(list(chunk_d)[-req_samples:])
            else:
                logger.debug(f"Pushing: {chunk[-1]=}")
                outlet.push_sample([chunk[-1]])

            # for s in :
            #     outlet.push_sample([s])

            sw.n_new = 0
            tlast = pylsl.local_clock()

            # sleep_s to free up a bit of compute
            sleep_s((1 / srate) * 0.95)


def get_main_thread() -> tuple[threading.Thread, threading.Event]:
    stop_event = threading.Event()
    stop_event.clear()

    thread = threading.Thread(target=main, kwargs={"stop_event": stop_event})
    thread.start()

    return thread, stop_event


if __name__ == "__main__":
    logger.setLevel(10)
    Fire(main)
