# Behavioral specification

With frame-aware limiting enabled, once the first beat of a frame is accepted, an idle gap before the final beat must not cause that continuing frame to be treated as a new frame or spuriously backpressured.
