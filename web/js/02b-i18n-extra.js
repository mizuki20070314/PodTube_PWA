/* Strings that only the PWA needs (the access key, installing, the bookmarklet ...) and the few of the original app that
   mention things a web app does not have (the Keychain, Safari on the device). */
(function (PT) {
  'use strict';
  var X = {
    'gate.placeholder': ['アクセスキー', 'Access key'],
    'gate.submit': ['開く', 'Open'],
    'gate.intro': ['このサーバーの PodTube を使うには、アクセスキーが必要です。', 'An access key is needed to use PodTube on this server.'],
    'gate.wrong': ['キーが違います', 'Wrong key'],
    'gate.note': ['キーはこのブラウザにだけ保存されます。', 'The key is stored in this browser only.'],
    'net.error': ['サーバーに接続できませんでした', "Couldn't reach the server"],
    'share.copied': ['リンクをコピーしました', 'Link copied'],
    'downloads.unsupported': ['このブラウザではダウンロードを使えません', "Downloads aren't available in this browser"],
    'downloads.quota': ['端末の保存容量が足りません', 'Not enough storage on this device'],
    'settings.app': ['アプリ', 'App'],
    'settings.addToHome': ['ホーム画面に追加', 'Add to Home Screen'],
    'settings.installed': ['ホーム画面から起動しています。', 'Running from the Home Screen.'],
    'settings.installIOS': ['Safari の共有ボタン（□↑）→「ホーム画面に追加」で、アプリのように起動できます。',
      'In Safari, tap the Share button, then "Add to Home Screen", to open PodTube like an app.'],
    'settings.installOther': ['ブラウザのメニューの「アプリをインストール」または「ホーム画面に追加」で、アプリのように起動できます。',
      'Use "Install app" or "Add to Home screen" in the browser menu to open PodTube like an app.'],
    'settings.bookmarklet': ['ブックマークレットをコピー', 'Copy bookmarklet'],
    'settings.bookmarkletCopied': ['ブックマークレットをコピーしました', 'Bookmarklet copied'],
    'settings.bookmarkletHint': ['YouTube のページから PodTube で開くには、コピーしたものをブックマークの URL に登録します。',
      'To open a YouTube page in PodTube, save the copied text as the URL of a bookmark.'],
    'settings.update': ['アプリを更新', 'Update app'],
    'settings.updated': ['新しいバージョンに更新しました', 'Updated to the new version'],
    'settings.upToDate': ['最新の状態です', 'Already up to date'],
    'settings.storage': ['ダウンロードの容量', 'Download storage'],
    'settings.forgetKey': ['この端末のアクセスキーを削除', "Forget this device's access key"],
    'settings.forgetKeyHint': ['削除すると、次に開くときにアクセスキーの入力が必要になります。', 'You will have to enter the access key again next time.'],
    'settings.clearCache': ['キャッシュを消去', 'Clear cache'],
    'signin.step1': ['① この端末のブラウザか、別の端末（パソコン・スマホ）で次のページを開く',
      '1. In the browser of this device, or on another device (computer / phone), open'],
    'signin.note': ['パスワードはこのアプリには入力されません。ログイン情報（トークン）はこのブラウザにだけ保存され、「ログアウト」で削除と失効が行われます。非公式のため、YouTube の TV アプリと同じ機器コード方式を使っています。',
      'Your password is never typed into this app. The sign-in token is kept only in this browser and is deleted and revoked when you sign out. Because this is an unofficial app it uses the same device-code method as the YouTube TV app.']
  };
  for (var k in X) PT.L10N[k] = X[k];
})(window.PT);
