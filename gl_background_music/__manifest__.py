{
    "name": "Hintergrundmusik",
    "summary": "Spotify Connect Fernbedienung mit Windows-Wiedergaberechner",
    "version": "19.0.1.0.1",
    "category": "Productivity",
    "license": "LGPL-3",
    "author": "Groundlift",
    "depends": ["base", "web"],
    "data": [
        "security/music_security.xml",
        "security/ir.model.access.csv",
        "views/music_views.xml",
        "views/settings_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "gl_background_music/static/src/music.js",
            "gl_background_music/static/src/music.xml",
            "gl_background_music/static/src/music.scss",
        ],
    },
    "application": True,
    "installable": True,
}
