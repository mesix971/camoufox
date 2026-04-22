"""
Profile -> Camoufox config dict.

The output keys and types are the authoritative schema from
`settings/properties.json`. The dict can be passed directly to
`camoufox.utils.launch_options(config=...)`.

Keys we deliberately do NOT emit:
    - navigator.productSub: Camoufox docs say never override it.
    - navigator.buildID: Camoufox fills it from its own build. Emit only if the
      caller explicitly forces it (off by default).
    - webGl:parameters / shaderPrecisionFormats / contextAttributes: these are
      deep GPU dicts that need a dedicated renderer-aware generator. Out of
      scope for v1 — let Camoufox's defaults handle them.
    - canvas:aaOffset / aaCapOffset: canvas randomization belongs to the closed
      portion of Camoufox; we don't touch it.
"""

from __future__ import annotations

from typing import Any, Dict

from fpgen.profile import Profile


def to_camoufox_config(p: Profile, include_build_id: bool = False) -> Dict[str, Any]:
    """Render the Profile as a Camoufox config dict."""
    cfg: Dict[str, Any] = {
        # navigator
        "navigator.userAgent": p.user_agent,
        "navigator.appCodeName": "Mozilla",
        "navigator.appName": "Netscape",
        "navigator.appVersion": p.app_version,
        "navigator.oscpu": p.oscpu,
        "navigator.platform": p.platform,
        "navigator.product": "Gecko",
        "navigator.hardwareConcurrency": p.cpu_cores,
        "navigator.maxTouchPoints": p.max_touch_points,
        "navigator.language": p.language,
        "navigator.languages": list(p.languages),
        "navigator.doNotTrack": p.dnt,
        "navigator.globalPrivacyControl": p.global_privacy_control,
        "navigator.cookieEnabled": True,
        "navigator.onLine": True,

        # screen
        "screen.width": p.screen_width,
        "screen.height": p.screen_height,
        "screen.availWidth": p.avail_width,
        "screen.availHeight": p.avail_height,
        "screen.availLeft": 0,
        "screen.availTop": 0,
        "screen.colorDepth": p.color_depth,
        "screen.pixelDepth": p.color_depth,

        # window
        "window.outerWidth": p.outer_width,
        "window.outerHeight": p.outer_height,
        "window.innerWidth": p.inner_width,
        "window.innerHeight": p.inner_height,
        "window.screenX": p.screen_x,
        "window.screenY": p.screen_y,
        "window.devicePixelRatio": p.device_pixel_ratio,

        # headers
        "headers.Accept-Language": p.accept_language,

        # locale
        "locale:all": p.locale,
        "locale:language": p.language,
        "locale:region": p.region,

        # timezone + geo
        "timezone": p.timezone,
        "geolocation:latitude": p.latitude,
        "geolocation:longitude": p.longitude,
        "geolocation:accuracy": p.geo_accuracy,

        # audio
        "AudioContext:sampleRate": p.audio_sample_rate,
        "AudioContext:outputLatency": p.audio_output_latency,
        "AudioContext:maxChannelCount": p.audio_max_channel_count,

        # webgl — note: properties.json does not list webGl2:vendor/renderer,
        # only the extensions/parameters maps. Firefox's WebGL2 context reuses
        # the WebGL1 vendor/renderer strings by default.
        "webGl:vendor": p.webgl_vendor,
        "webGl:renderer": p.webgl_renderer,

        # fonts
        "fonts": list(p.fonts),
        "fonts:spacing_seed": p.fonts_spacing_seed,

        # media devices
        "mediaDevices:enabled": p.media_enabled,
        "mediaDevices:webcams": p.media_webcams,
        "mediaDevices:micros": p.media_micros,
        "mediaDevices:speakers": p.media_speakers,

        # battery
        "battery:charging": p.battery_charging,
        "battery:level": p.battery_level,
        "battery:chargingTime": p.battery_charging_time,
        "battery:dischargingTime": p.battery_discharging_time,
    }

    if include_build_id and p.build_id:
        cfg["navigator.buildID"] = p.build_id

    return cfg
