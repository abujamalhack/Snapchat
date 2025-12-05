{pkgs}: {
  deps = [
    pkgs.python310
    pkgs.ffmpeg
    pkgs.libwebp
    pkgs.pkg-config
    pkgs.openssl
    pkgs.zlib
  ];
}