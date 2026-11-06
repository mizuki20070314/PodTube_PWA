"""iOS behaviour of the fullscreen button and Picture in Picture, with the WebKit-only APIs stood in for by mocks.

Headless Edge is not Safari, so this checks OUR side: which route the button takes on iPhone / iPad / Home Screen apps / Android,
that the OS video player is asked for inside the tap, that the state is followed, the captions mirror, and what PiP does when iOS
refuses it (a Home Screen app) - the way the real WebKit answers were measured in WebKit bug 303885.  It does not prove that iOS itself
behaves that way: that needs a device.

usage: python tests/t_ios.py [url]        (the dev server must run: python tests/devserver.py 8080)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.makedirs(os.path.join(HERE, "shots"), exist_ok=True)
import cdp  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/podtube/"
IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
IPAD = "Mozilla/5.0 (iPad; CPU OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print("%s %-66s %s" % ("PASS" if ok else "FAIL", name, detail))


MOCKS = r"""
(function () {
  var v = document.querySelector('.w-player video');
  var S = window.__ios = { v: v, calls: [], displaying: false, pipMode: 'inline', supportsFs: true, enterThrows: false,
    stdPip: true, stdPipOk: true, wkPip: true, ua: navigator.userAgent, fsApi: true, origUA: navigator.userAgent };
  function define(obj, name, getter) { Object.defineProperty(obj, name, { configurable: true, get: getter }); }
  define(navigator, 'userAgent', function () { return S.ua; });
  define(document, 'fullscreenEnabled', function () { return S.fsApi; });
  define(document, 'webkitFullscreenEnabled', function () { return S.fsApi; });
  var watch = document.querySelector('.watch');
  watch.requestFullscreen = function () {
    S.calls.push('elFs');
    return S.elFsRejects ? Promise.reject(new TypeError('Fullscreen request denied')) : Promise.resolve();
  };
  // the OS video player (iOS): only on the <video>, inside a tap
  define(v, 'webkitSupportsFullscreen', function () { return S.supportsFs && v.readyState >= 1 && v.videoWidth > 0; });
  define(v, 'webkitDisplayingFullscreen', function () { return S.displaying; });
  v.webkitEnterFullscreen = function () {
    S.calls.push('enterFs');
    if (S.enterThrows) throw new Error('InvalidStateError');
    S.displaying = true;
    setTimeout(function () { v.dispatchEvent(new Event('webkitbeginfullscreen')); }, 20);
  };
  v.webkitExitFullscreen = function () {
    S.calls.push('exitFs');
    S.displaying = false;
    setTimeout(function () { v.dispatchEvent(new Event('webkitendfullscreen')); }, 20);
  };
  // Picture in Picture: the standard API and the WebKit one
  define(document, 'pictureInPictureEnabled', function () { return S.stdPip; });
  v.requestPictureInPicture = function () {
    S.calls.push('stdPip');
    return S.stdPipOk ? Promise.resolve({}) : Promise.reject(new DOMException('The video element does not support the Picture-in-Picture mode.', 'NotSupportedError'));
  };
  v.webkitSupportsPresentationMode = function (m) { return m === 'picture-in-picture' ? !!S.wkPip : true; };
  v.webkitSetPresentationMode = function (m) {
    S.calls.push('wkSet:' + m);
    if (S.wkSilent) return;                                   // WebKit accepts the call and nothing happens
    S.pipMode = m; v.dispatchEvent(new Event('webkitpresentationmodechanged'));
  };
  define(v, 'webkitPresentationMode', function () { return S.pipMode; });
  S.reset = function () {
    S.calls = []; S.displaying = false; S.pipMode = 'inline'; S.supportsFs = true; S.enterThrows = false;
    S.stdPip = true; S.stdPipOk = true; S.wkPip = true; S.wkSilent = false; S.fsApi = true; S.elFsRejects = false; S.ua = S.origUA;
    PT.isIOS = false; PT.standalone = false; PT.settings.iosFullscreen = 'native';
    PT.watch.exitFullscreen();
  };
  S.click = function (sel) { document.querySelector(sel).click(); };
  return 'mocks installed on ' + v.parentElement.className;
})()
"""


def setup(b, ios, standalone=False, ua=None, fs_api=True, **flags):
    b.js("__ios.reset()")
    b.js("PT.isIOS = %s; PT.standalone = %s; __ios.fsApi = %s;" % (str(ios).lower(), str(standalone).lower(), str(fs_api).lower()))
    if ua:
        b.js("__ios.ua = %r" % ua)
    for k, v in flags.items():
        b.js("__ios.%s = %s" % (k, str(v).lower() if isinstance(v, bool) else repr(v)))
    b.js("PT.emit('player')")                       # the controls look again at PiP / fullscreen
    b.pump(0.3)


def calls(b):
    return b.js("__ios.calls.join(',')")


def is_fs(b):
    return b.js("document.querySelector('.watch').classList.contains('fs')")


def toast(b):
    return b.js("(document.querySelector('.toast')||{}).textContent || ''")


def fs_icon_is(b, name):
    """Is the fullscreen button showing icon `name`?  (both sides go through the HTML parser: it re-serialises SVG)"""
    return b.js("(function(){var e=document.createElement('div');e.innerHTML=PT.iconSvg(%r,26);return e.innerHTML===document.querySelector('.ctl-fs').innerHTML})()" % name) is True


with cdp.Browser(size=(430, 900), scale=2.0) as b:
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0)
    b.open(URL, wait=4)
    b.js("localStorage.clear()")
    b.js("PT.settings.uiLanguage = 'ja'")
    b.js("PT.router.play({id:'dQw4w9WgXcQ', title:'x'})")
    b.pump(8)
    check("a video is playing (needed for the mocks)", b.js("PT.player.state") == "playing" and b.js("document.querySelector('.w-player video').videoWidth") > 0)
    print(b.js(MOCKS))

    # ------------------------------------------------------------------ fullscreen
    print("\n-- fullscreen: where the button goes")
    setup(b, True, ua=IPHONE, fs_api=False)
    check("iPhone Safari: route is the OS video player", b.js("PT.watch.fullscreenRoute()") == "video", b.js("PT.watch.fullscreenInfo()"))
    check("iPhone Safari: the setting is offered", b.js("PT.watch.hasFullscreenChoice()") is True)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.3)
    check("iPhone: tap -> webkitEnterFullscreen() once, no CSS fullscreen", calls(b) == "enterFs" and not is_fs(b), calls(b))
    check("iPhone: the OS player is tracked as active", b.js("PT.player.videoFullscreen.active") is True)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.3)
    check("iPhone: tap again -> webkitExitFullscreen(), state back", calls(b) == "enterFs,exitFs" and b.js("PT.player.videoFullscreen.active") is False, calls(b))
    b.pump(1.0)
    check("iPhone: after the OS player the layout is normal", not is_fs(b))

    setup(b, True, ua=IPHONE, fs_api=False)
    b.js("PT.settings.iosFullscreen = 'app'")
    check("iPhone, setting 'in the app': route is css", b.js("PT.watch.fullscreenRoute()") == "css")
    b.js("__ios.click('.ctl-fs')"); b.pump(0.4)
    check("iPhone, 'in the app': fills the window (CSS), OS player not asked", is_fs(b) and calls(b) == "", calls(b))
    check("  ... and the icon says 'leave fullscreen'", fs_icon_is(b, "fullscreen_exit"))
    b.js("__ios.click('.ctl-fs')"); b.pump(0.4)
    check("iPhone, 'in the app': tap again leaves it", not is_fs(b))
    check("  ... and the icon says 'fullscreen' again", fs_icon_is(b, "fullscreen"))

    setup(b, True, ua=IPHONE, fs_api=False, supportsFs=False)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.4)
    check("iPhone, webkitSupportsFullscreen false -> CSS fallback", is_fs(b) and calls(b) == "", calls(b))

    setup(b, True, ua=IPHONE, fs_api=False, enterThrows=True)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.4)
    check("iPhone, webkitEnterFullscreen() throws -> CSS fallback", is_fs(b) and calls(b) == "enterFs", calls(b))

    setup(b, True, ua=IPAD, fs_api=True)
    check("iPad in Safari: route is the Fullscreen API on the player", b.js("PT.watch.fullscreenRoute()") == "element")
    check("iPad in Safari: no setting needed", b.js("PT.watch.hasFullscreenChoice()") is False)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.3)
    check("iPad in Safari: tap -> requestFullscreen on the player", calls(b) == "elFs", calls(b))

    setup(b, True, ua=IPAD, fs_api=True, elFsRejects=True)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.5)
    check("iPad in Safari, Fullscreen API refused -> the OS video player next", calls(b) == "elFs,enterFs", calls(b))

    setup(b, True, ua=IPAD, fs_api=True, elFsRejects=True)
    b.js("PT.settings.iosFullscreen = 'app'")
    b.js("__ios.click('.ctl-fs')"); b.pump(0.5)
    check("  ... with the setting 'in the app' -> the window is filled instead", calls(b) == "elFs" and is_fs(b), calls(b))

    setup(b, True, standalone=True, ua=IPAD, fs_api=True)
    check("iPad Home Screen app: route is the OS video player", b.js("PT.watch.fullscreenRoute()") == "video", b.js("PT.watch.fullscreenInfo()"))
    b.js("__ios.click('.ctl-fs')"); b.pump(0.3)
    check("iPad Home Screen app: tap -> webkitEnterFullscreen()", calls(b) == "enterFs", calls(b))
    b.js("__ios.reset()"); b.pump(0.5)

    setup(b, False, fs_api=True)
    check("Android / desktop: route is the Fullscreen API (unchanged)", b.js("PT.watch.fullscreenRoute()") == "element")
    b.js("__ios.click('.ctl-fs')"); b.pump(0.3)
    check("Android / desktop: tap -> requestFullscreen on the player", calls(b) == "elFs", calls(b))
    b.js("__ios.reset()"); b.pump(0.5)

    print("\n-- iPhone held sideways (laid out like fullscreen, but not one)")
    setup(b, True, ua=IPHONE, fs_api=False)
    cdp.emulate(b, 800, 390, mobile=True, scale=2.0); b.pump(1.5)
    check("landscape: laid out as fullscreen", b.js("PT.watch.fullscreenLayout()") is True)
    check("landscape: the icon still offers 'fullscreen' (it is not a real one yet)", fs_icon_is(b, "fullscreen"))
    b.shot("shots/ios_landscape.png")
    b.js("__ios.click('.ctl-fs')"); b.pump(0.3)
    check("landscape: the button makes it a real fullscreen (OS player)", calls(b) == "enterFs", calls(b))
    b.js("__ios.click('.ctl-fs')"); b.pump(0.5)
    cdp.emulate(b, 390, 800, mobile=True, scale=2.0); b.pump(1.5)
    b.js("__ios.reset()"); b.pump(0.5)

    # ------------------------------------------------------------------ Picture in Picture
    print("\n-- Picture in Picture")
    # what WebKit answers in a Home Screen app (WebKit bug 303885): the page flag says yes, WebKit says no, the request is refused
    setup(b, True, standalone=True, ua=IPHONE, fs_api=False, stdPip=True, stdPipOk=False, wkPip=False)
    check("Home Screen app: state is 'blocked'", b.js("PT.player.pip.state") == "blocked", b.js("PT.player.pip.info()"))
    check("Home Screen app: the button stays but is dimmed",
          b.js("(function(){var e=document.querySelector('.ctl-pip');return !e.hidden && e.classList.contains('dim')})()") is True)
    b.js("__ios.click('.ctl-pip')"); b.pump(0.5)
    t = toast(b)
    check("Home Screen app: a tap says why (iOS limitation, use Safari)", "ホーム画面" in t and "Safari" in t, repr(t))
    check("Home Screen app: no useless PiP request was made", calls(b) == "", calls(b))
    b.shot("shots/ios_pip_blocked_toast.png")
    b.pump(3.5)

    setup(b, True, standalone=False, ua=IPHONE, fs_api=False, stdPip=True, stdPipOk=False, wkPip=False)
    b.js("__ios.click('.ctl-pip')"); b.pump(0.5)
    t = toast(b)
    check("blocked but not a Home Screen app: the generic message", "開始できませんでした" in t, repr(t))
    b.pump(3.5)

    setup(b, True, standalone=False, ua=IPHONE, fs_api=False, stdPip=True, stdPipOk=False, wkPip=True)
    check("Safari: state is 'ready'", b.js("PT.player.pip.state") == "ready")
    b.js("__ios.click('.ctl-pip')"); b.pump(0.6)
    check("Safari, standard request refused -> tries the WebKit call", calls(b) == "stdPip,wkSet:picture-in-picture", calls(b))
    check("  ... and PiP is active", b.js("PT.player.pip.active") is True)
    b.js("__ios.click('.ctl-pip')"); b.pump(0.4)
    check("  ... a second tap leaves it", calls(b).endswith("wkSet:inline") and b.js("PT.player.pip.active") is False, calls(b))

    setup(b, True, standalone=True, ua=IPHONE, fs_api=False, stdPip=True, stdPipOk=False, wkPip=True, wkSilent=True)
    b.js("__ios.click('.ctl-pip')"); b.pump(0.5)
    check("WebKit call accepted but silent: nothing is claimed at first", calls(b) == "stdPip,wkSet:picture-in-picture" and "ホーム画面" not in toast(b), calls(b))
    b.pump(1.6)
    t = toast(b)
    check("  ... and after a moment the app says why it did not work", "ホーム画面" in t, repr(t))
    b.pump(3.5)

    setup(b, True, standalone=False, ua=IPHONE, fs_api=False, stdPip=False, wkPip=False)
    check("iOS 12 style (no PiP at all): state is 'none', button hidden",
          b.js("PT.player.pip.state") == "none" and b.js("document.querySelector('.ctl-pip').hidden") is True)

    setup(b, False, fs_api=True, stdPip=True, stdPipOk=True, wkPip=False)
    b.js("delete __ios.v.webkitSupportsPresentationMode")
    check("Chrome / Edge / Android: state is 'ready' (standard API only)", b.js("PT.player.pip.state") == "ready")
    b.js("__ios.click('.ctl-pip')"); b.pump(0.4)
    check("Chrome / Edge / Android: the standard request is used", calls(b) == "stdPip", calls(b))

    # ------------------------------------------------------------------ captions for the OS player
    print("\n-- captions mirrored for the OS video player")
    b.js("__ios.v.webkitSupportsPresentationMode = function (m) { return true; }")
    setup(b, True, ua=IPHONE, fs_api=False)
    b.js("PT.subtitles.current = {i: 0, name: 'test', languageCode: 'en'}; PT.subtitles.cues = [[1, 3, 'a & b <i>'], [4, 6, 'second']]; PT.emit('subtitles')")
    b.pump(0.3)
    info = b.js("(function(){var t=Array.prototype.filter.call(__ios.v.textTracks,function(x){return x.label==='PodTube'})[0];"
                "return t?JSON.stringify({kind:t.kind,mode:t.mode,n:t.cues.length,first:t.cues[0].text}):'none'})()")
    check("a hidden TextTrack with the cues exists", '"n":2' in str(info) and '"mode":"hidden"' in str(info), info)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.4)
    mode = b.js("Array.prototype.filter.call(__ios.v.textTracks,function(x){return x.label==='PodTube'})[0].mode")
    check("entering the OS player shows the captions track", mode == "showing", mode)
    b.js("__ios.click('.ctl-fs')"); b.pump(0.4)
    mode = b.js("Array.prototype.filter.call(__ios.v.textTracks,function(x){return x.label==='PodTube'})[0].mode")
    check("leaving it hides the track again (the app's own overlay shows them)", mode == "hidden", mode)
    b.js("PT.subtitles.current = null; PT.subtitles.cues = []; PT.emit('subtitles')"); b.pump(0.3)
    n = b.js("Array.prototype.filter.call(__ios.v.textTracks,function(x){return x.label==='PodTube'})[0].cues.length")
    check("captions off: the cues are removed", n == 0, n)

    # ------------------------------------------------------------------ settings screen + diagnostics
    print("\n-- settings and diagnostics")
    setup(b, True, ua=IPHONE, fs_api=False)
    b.js("PT.watch.setMinimized(true, false)"); b.pump(0.5)
    b.js("PT.router.openSettings()"); b.pump(1.0)
    txt = b.js("document.querySelector('.settings').innerText")
    check("settings (iPhone): the fullscreen choice is there", "全画面表示" in txt and "OS 標準" in txt, "")
    b.js("document.querySelector('.settings').scrollTop = 250"); b.pump(0.5)
    b.shot("shots/ios_settings.png")
    b.js("PT.nav.popToRoot()"); b.pump(0.6)
    setup(b, False, fs_api=True)
    b.js("PT.router.openSettings()"); b.pump(1.0)
    txt = b.js("document.querySelector('.settings').innerText")
    check("settings (desktop): the choice is not shown", "OS 標準のプレーヤー" not in txt)
    errs = [m for m in b.console_messages() if m.startswith(("EXCEPTION", "error"))]
    check("no script errors in the console", not errs, str(errs[:3]))

print("\n%d/%d passed" % (sum(results), len(results)))
sys.exit(0 if all(results) else 1)
