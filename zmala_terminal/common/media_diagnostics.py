"""Read native statistics without consuming media or changing device power.

The engine owns the call; each statistics snapshot has its own native reference.
"""
import math


# @llr LLR-TERM-MAINT-018
def media_stats(engine, backend, windows):
    result = {}
    if engine.call:
        if not windows:
            result['codecs'] = backend.codec_stats(engine)
        for kind, getter in [('audio', engine.call_get_audio_stats), ('video', engine.call_get_video_stats)]:
            stats = getter(engine.call)
            if stats:
                try:
                    result[kind] = {'download_kbps': engine.call_stats_get_download_bandwidth(stats),
                                    'upload_kbps': engine.call_stats_get_upload_bandwidth(stats),
                                    'jitter_buffer_ms': engine.call_stats_get_jitter_buffer_size_ms(stats),
                                    'round_trip_seconds': engine.call_stats_get_round_trip_delay(stats),
                                    'receiver_loss_percent': engine.call_stats_get_receiver_loss_rate(stats),
                                    'sender_loss_percent': engine.call_stats_get_sender_loss_rate(stats)}
                finally:
                    engine.call_stats_unref(stats)
        for kind in ('audio', 'video'):
            if kind in result:
                # SDK sentinel values mean unavailable, not negative latency/loss.
                result[kind] = {key: value for key, value in result[kind].items()
                                if math.isfinite(value) and 0 <= value <= 9007199254740991}
        if 'video' in result:
            params = engine.call_get_current_params(engine.call)
            if params:
                result['video']['received_fps'] = engine.call_params_get_received_framerate(params)
                result['video']['sent_fps'] = engine.call_params_get_sent_framerate(params)
                for key in ('received_fps', 'sent_fps'):
                    if not math.isfinite(result['video'][key]) or result['video'][key] < 0:
                        del result['video'][key]
                for direction in ('sent', 'received'):
                    size = getattr(engine, 'call_params_get_'+direction+'_video_size')(params)
                    if size.width > 0 and size.height > 0:
                        result['video'][direction+'_resolution'] = [size.width, size.height]
    return result

