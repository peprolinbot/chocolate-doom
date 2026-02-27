# https://github.com/NixOS/nixpkgs/blob/nixos-25.11/pkgs/by-name/ch/chocolate-doom/package.nix

{
  lib,
  stdenv,
  autoreconfHook,
  libpng,
  libsamplerate,
  pkg-config,
  python3,
  SDL2,
  SDL2_mixer,
  SDL2_net,
}:

stdenv.mkDerivation (finalAttrs: {
  pname = "chocolate-doom";
  version = "H4ckUDC26";

  src = ./.;

  postPatch = ''
    patchShebangs --build man/{simplecpp,docgen}
  '';

  nativeBuildInputs = [
    autoreconfHook
    pkg-config
    # for documentation
    python3
  ];

  buildInputs = [
    libpng
    libsamplerate
    SDL2
    SDL2_mixer
    SDL2_net
  ];

  outputs = [
    "out"
    "man"
  ];

  enableParallelBuilding = true;

  strictDeps = true;

  meta = {
    homepage = "https://www.chocolate-doom.org";
    changelog = "https://github.com/chocolate-doom/chocolate-doom/releases/tag/chocolate-doom-${finalAttrs.version}";
    description = "Doom source port that accurately reproduces the experience of Doom as it was played in the 1990s";
    mainProgram = "chocolate-doom";
    license = lib.licenses.gpl2Plus;
    platforms = lib.platforms.unix;
    maintainers = with lib.maintainers; [ Gliczy ];
  };
})
