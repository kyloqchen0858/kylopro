import antigravity
import sys
import webbrowser
from unittest.mock import patch, MagicMock
import pytest

def test_antigravity_import():
    """Test that antigravity can be imported without errors."""
    assert 'antigravity' in sys.modules

def test_antigravity_has_geohash():
    """Test that antigravity exposes the geohash function."""
    assert hasattr(antigravity, 'geohash')
    assert callable(antigravity.geohash)

def test_geohash_signature():
    """Check the geohash function signature via inspection."""
    import inspect
    sig = inspect.signature(antigravity.geohash)
    params = list(sig.parameters.keys())
    # Expected parameters: latitude, longitude, datedow
    assert params == ['latitude', 'longitude', 'datedow']
    # Check default for datedow is None
    assert sig.parameters['datedow'].default is None

def test_antigravity_has_link():
    """Test that antigravity has the comic link function."""
    assert hasattr(antigravity, 'link')
    assert callable(antigravity.link)

@patch('webbrowser.open')
def test_link_function(mock_open: MagicMock):
    """Test that antigravity.link opens the correct URL."""
    antigravity.link()
    # Verify webbrowser.open was called exactly once
    mock_open.assert_called_once()
    # Get the URL argument
    args, _ = mock_open.call_args
    url = args[0]
    # Check it's the expected XKCD comic
    assert url == "https://xkcd.com/353/"

def test_antigravity_docstring():
    """Ensure the module has a docstring."""
    assert antigravity.__doc__ is not None
    assert "antigravity" in antigravity.__doc__

# Example of using geohash (not a strict test, but demonstrates usage)
def test_geohash_example():
    """Example usage of geohash - not a strict assertion test."""
    # This is the example from the antigravity source code
    result = antigravity.geohash(37.421542, -122.085589, b'2005-05-26-10458.68')
    # The geohash is deterministic, so we can check the known output
    expected = b'37.857713 -122.544543'
    assert result == expected

if __name__ == "__main__":
    # Run basic tests if script is executed directly
    test_antigravity_import()
    print("✓ antigravity imported")
    test_antigravity_has_geohash()
    print("✓ geohash function present")
    test_geohravity_has_link()
    print("✓ link function present")
    test_geohash_signature()
    print("✓ geohash signature correct")
    test_antigravity_docstring()
    print("✓ module has docstring")
    # Mock test for link
    with patch('webbrowser.open'):
        test_link_function(MagicMock())
    print("✓ link function opens correct URL")
    test_geohash_example()
    print("✓ geohash example produces expected output")
    print("\nAll direct tests passed!")
    # Note: For full pytest compatibility, run with `pytest test_antigravity.py`