with import <nixpkgs> {};
mkShell {
  buildInputs = [
    pkgs.python3
    pkgs.python3Packages.virtualenv
  ];

  shellHook = ''
    virtualenv venv
    source ./venv/bin/activate
    pip install -r requirements-dev.txt
  '';
}
