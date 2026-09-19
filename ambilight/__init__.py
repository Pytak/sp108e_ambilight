"""SP108E Ambilight: stream screen colours to an SP108E LED controller.

Modules:
    config    settings dataclass, JSON file and its location
    protocol  SP108E packets, status, brightness, preview frames
    capture   monitor list, band region, GDI grabber, capture thread
    streamer  the stream thread that feeds the controller
"""
