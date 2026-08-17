$root = $PSScriptRoot
$port = 8743
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$port/")
$listener.Start()
Write-Host "Serving $root on http://localhost:$port/"

$mime = @{
  ".html"="text/html; charset=utf-8"; ".css"="text/css"; ".js"="application/javascript";
  ".jpg"="image/jpeg"; ".jpeg"="image/jpeg"; ".png"="image/png"; ".svg"="image/svg+xml";
  ".mp4"="video/mp4"; ".json"="application/json"; ".ico"="image/x-icon"
}

while ($listener.IsListening) {
  try {
    $context = $listener.GetContext()
    $req = $context.Request
    $res = $context.Response
    try {
      $path = $req.Url.LocalPath
      if ($path -eq "/") { $path = "/index.html" }
      $filePath = Join-Path $root ($path.TrimStart("/"))
      if ((Test-Path $filePath -PathType Leaf)) {
        $ext = [System.IO.Path]::GetExtension($filePath)
        $ct = $mime[$ext]
        if (-not $ct) { $ct = "application/octet-stream" }
        $fs = [System.IO.File]::OpenRead($filePath)
        try {
          $res.StatusCode = 200
          $res.ContentType = $ct
          $res.ContentLength64 = $fs.Length
          $fs.CopyTo($res.OutputStream)
        } finally { $fs.Close() }
      } else {
        $msg = [System.Text.Encoding]::UTF8.GetBytes("404 Not Found")
        $res.StatusCode = 404
        $res.ContentLength64 = $msg.Length
        $res.OutputStream.Write($msg, 0, $msg.Length)
      }
    } catch {
      Write-Host "Request error: $_"
    } finally {
      try { $res.OutputStream.Close() } catch {}
    }
  } catch {
    Write-Host "Listener error: $_"
  }
}
