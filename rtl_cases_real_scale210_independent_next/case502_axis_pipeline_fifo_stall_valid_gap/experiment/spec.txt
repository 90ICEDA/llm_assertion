Once an output beat is valid, a downstream stall must hold both valid and payload until a ready handshake. Repeated stalled cycles cannot create a valid gap or overwrite the buffered beat.
