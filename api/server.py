from fire import Fire

from dareplane_utils.default_server.server import DefaultServer

from passthrough_decoder.utils.logging import logger
from passthrough_decoder.main import get_main_thread


def main(port: int = 8080, ip: str = "127.0.0.1", loglevel: int = 10):
    logger.setLevel(loglevel)
    pcommand_map = {"START": get_main_thread}

    logger.debug(
        f"Defining dp-passthrough server on {ip}:{port} with log level {loglevel} ..."
    )
    server = DefaultServer(
        port, ip=ip, pcommand_map=pcommand_map, name="passthrough_server"
    )

    # initialize to start the socket
    logger.debug("Initializing dp-passthrough server socket")
    server.init_server()
    # start processing of the server
    logger.debug("Starting dp-passthrough server listening loop")
    server.start_listening()

    return 0


if __name__ == "__main__":
    Fire(main)
