# Homebrew formula for hwh - Hardware Hacking Toolkit
#
# To install from tap:
#   brew tap ResistanceIsUseless/hwh https://github.com/ResistanceIsUseless/hwh
#   brew install hwh
#
# Or install directly:
#   brew install ResistanceIsUseless/hwh/hwh

class Hwh < Formula
  include Language::Python::Virtualenv

  desc "Hardware Hacking Toolkit - Multi-device TUI for hardware security research"
  homepage "https://github.com/ResistanceIsUseless/hwh"
  url "https://github.com/ResistanceIsUseless/hwh/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "PLACEHOLDER_SHA256"  # Update after first release
  license "MIT"
  head "https://github.com/ResistanceIsUseless/hwh.git", branch: "main"

  depends_on "python@3.11"

  resource "textual" do
    url "https://files.pythonhosted.org/packages/source/t/textual/textual-0.47.1.tar.gz"
    sha256 "PLACEHOLDER"  # Update with actual sha256
  end

  resource "pyserial" do
    url "https://files.pythonhosted.org/packages/source/p/pyserial/pyserial-3.5.tar.gz"
    sha256 "3c77e014170dfffbd816e6ffc205e9842e6c13e0f02beb59ebd5a3a0c7e07ecc"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/source/r/rich/rich-13.7.0.tar.gz"
    sha256 "5cb5f1ab7e456a8d47f5eb4de80c41b1d1db3e4d90e80d84d2d93ced6db1a0c8"
  end

  resource "click" do
    url "https://files.pythonhosted.org/packages/source/c/click/click-8.1.7.tar.gz"
    sha256 "ca9853ad459e787e2192211578cc907e7594e294c7ccc834310722b41b9ca6de"
  end

  def install
    virtualenv_install_with_resources
  end

  def caveats
    <<~EOS
      hwh requires access to USB serial devices.
      You may need to add your user to the dialout group:
        sudo dseditgroup -o edit -a $(whoami) -t user dialout

      To use with Docker for device isolation:
        docker run -it --privileged -v /dev:/dev resistanceisuseless/hwh
    EOS
  end

  test do
    assert_match "Hardware Hacking Toolkit", shell_output("#{bin}/hwh --help")
    assert_match version.to_s, shell_output("#{bin}/hwh --version")
  end
end
