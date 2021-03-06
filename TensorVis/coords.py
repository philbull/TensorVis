
import numpy as np
import tensorflow as tf
from astropy.time import Time
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.coordinates import FK5, ICRS

FLOAT_TYPE = tf.float64

#HERA_LATITUDE = tf.constant(-30.7215*np.pi/180., dtype=FLOAT_TYPE)
HERA_LATITUDE = tf.constant(-0.5361917991288512, dtype=FLOAT_TYPE)
C = tf.constant(299792458., dtype=FLOAT_TYPE) # speed of light in m/s
PI = tf.constant(np.pi, dtype=FLOAT_TYPE)


@tf.function
def equatorial_to_topocentric(ra, dec, lst, latitude=HERA_LATITUDE):
    """
    Convert equatorial coordinates (RA, Dec) to topocentric coordinate 
    cosines (l, m, n).
    
    Parameters
    ----------
    ra, dec : array_like, float
        RA and Dec in radians.
    
    lst : array_like, float
        Local sidereal time, in radians.
    
    latitude : float, optional
        Latitude, in radians. Default: HERA_LATITUDE.
    
    Returns
    -------
    topo_cosines : Tensor
        Topocentric coordinate cosines, in order: (m, l, n).
    """
    # Equatorial cosines    
    eq_coords = tf.stack( [tf.math.cos(ra)*tf.math.cos(dec), 
                           tf.math.cos(dec)*tf.math.sin(ra),
                           tf.math.sin(dec)] )
    
    # Projection operator for equatorial cosines -> topocentric cosines
    topo_coords = tf.stack(
        [tf.stack([-tf.math.sin(lst), 
                    tf.math.cos(lst), 
                    tf.zeros_like(lst)]),
         tf.stack([-tf.math.sin(latitude) * tf.math.cos(lst), 
                   -tf.math.sin(latitude) * tf.math.sin(lst), 
                    tf.math.cos(latitude) * tf.ones_like(lst)]),
         tf.stack([ tf.math.cos(latitude) * tf.math.cos(lst), 
                    tf.math.cos(latitude) * tf.math.sin(lst), 
                    tf.math.sin(latitude) * tf.ones_like(lst)])] )
    
    # Return cosines l,m,n (N.B. this quantity is 'crd_top' in vis_cpu)
    print("eq_coords.shape:", eq_coords.shape)
    print("topo_coords.shape:", topo_coords.shape)
    topo_cosines = tf.tensordot(topo_coords, eq_coords, axes=[[1], [0]])
    return topo_cosines
    

@tf.function
def topocentric_to_az_za(l, m):
    """
    Convert angle cosines l,m to azimuth and zenith angle.
    
    Parameters
    ----------
    l, m : Tensor
        Topocentric angle cosines (dimensionless).
    
    Returns
    -------
    za : array_like, float
        Zenith angle, in radians.
    
    az : array_like, float
        Azimuth, in radians.
    """
    lsqr = l**2. + m**2.
    n = tf.where(lsqr < 1., tf.math.sqrt(1.-lsqr), 0.)
    az = -tf.math.atan2(m, l)
    za = PI/2. - tf.math.asin(n)
    return az, za


@tf.function
def topocentric_to_delay(topo_cosines, antpos):
    """
    Convert azimuth and zenith angle to geometric delay for each *antenna* 
    (i.e. not for a baseline).
    
    Parameters
    ----------
    topo_cosines : Tensor
        Tensor containing topocentric angle cosines (m, l, n).
    
    antpos : Tensor
        Tensor of antenna positions in topocentric Cartesian coordinates, 
        with shape (Nants, 3)
    
    Returns
    -------
    delay : array_like
        Geometric delay of each source per antenna. Shape: (az.size, Nants)
    """
    #alt = tf.constant(np.pi/2., dtype=FLOAT_TYPE) - za
    #coord_proj = tf.stack([-tf.math.sin(az)*tf.math.cos(alt), 
    #                       tf.math.cos(az)*tf.math.cos(alt),
    #                       tf.math.sin(alt)])
    
    # coord_proj = crd_top
    return tf.tensordot(antpos, topo_cosines, axes=[1,0]) / C



@tf.function
def eq_to_az_za(ra, dec, lst, latitude=HERA_LATITUDE):
    """
    Convert equatorial (RA/Dec) coordinates to azimuth and zenith angle.
    
    Basic expression from http://star-www.st-and.ac.uk/~fv/webnotes/chapter7.htm
    
    Parameters
    ----------
    ra, dec : array_like, float
        RA and Dec in radians.
    
    lst : array_like, float
        Local sidereal time, in radians.
    
    latitude : float, optional
        Latitude, in radians. Default: HERA_LATITUDE.
    
    Returns
    -------
    za : array_like, float
        Zenith angle, in radians.
    
    az : array_like, float
        Azimuth, in radians.
    """
    # FIXME: There is a bug in this code
    lat = latitude
    sin_alt = tf.math.sin(dec) * tf.math.sin(lat) \
            + tf.math.cos(dec) * tf.math.cos(lat) * tf.math.cos(lst - ra)
    alt = tf.math.asin(sin_alt)
    sin_az = tf.math.sin(ra - lst) * tf.math.cos(dec) / tf.math.cos(alt)
    cos_az = (tf.math.sin(dec) - tf.math.sin(lat) * sin_alt) \
           / (tf.math.cos(lat) * tf.math.cos(alt))
    return tf.constant(0.5*np.pi, dtype=FLOAT_TYPE) - alt, \
           tf.math.sign(tf.math.asin(sin_az)) * tf.math.acos(cos_az)


@tf.function
def az_za_to_delay(az, za, antpos):
    """
    Convert azimuth and zenith angle to geometric delay for each *antenna* 
    (i.e. not for a baseline).
    
    Parameters
    ----------
    az, za : array_like
        Azimuth and zenith angle of sources in radians.
    
    antpos : array_like
        Array of antenna positions in topocentric Cartesian coordinates, 
        with shape (Nants, 3)
    
    Returns
    -------
    delay : array_like
        Geometric delay of each source per antenna. Shape: (az.size, Nants)
    """
    alt = tf.constant(np.pi/2., dtype=FLOAT_TYPE) - za
    
    coord_proj = tf.stack([-tf.math.sin(az)*tf.math.cos(alt), 
                            tf.math.cos(az)*tf.math.cos(alt),
                            tf.math.sin(alt) ])
    
    # coord_proj = crd_top
    return tf.tensordot(antpos, coord_proj, axes=[1,0]) / C


def transform_coords():
    
    pos = SkyCoord(ra=ra[0]*u.deg, dec=dec[0]*u.deg, frame='icrs')

    ObsStartTime = Time(times[0], scale='utc', format='jd', location=hera_location)

    frame_2020 = FK5(equinox=Time(2020, format='jyear'))
    frame_current = FK5(equinox=ObsStartTime)
    pos_current = pos.transform_to(frame_current)
    pos_2020 = pos.transform_to(frame_2020)
    print(pos)
    print(pos_current)
    print(pos_2020)


def compare_coords(ra, dec, times, lsts, use_cirs=False):
    """
    Compare astropy vs homebrew coordinate conversion.
    
    ra, dec : degrees
    times : JD
    lsts: radians
    """
    # (1) Set-up Astropy calculation
    # Times in JD, RA and Dec in radians
    ct = hs.visibilities.AzZaTransforms(times[0,], ra*np.pi/180., dec*np.pi/180., 
                                        precompute=False, astropy=True)
    az_za_astropy = [ct.call_astropy(ra*u.deg, dec*u.deg, t) for t in times]
    az_za_astropy = np.array(az_za_astropy)
    astropy_az = az_za_astropy[:,0,:]
    astropy_za = az_za_astropy[:,1,:]
    
    # (2) Convert coords to current (2020) epoch
    ObsStartTime = Time(times[0], scale='utc', format='jd', location=hera_location)
    if use_cirs:
        frame_now = CIRS(obstime=ObsStartTime)
    else:
        frame_now = FK5(equinox=ObsStartTime)
    
    # Convert coords
    pos = SkyCoord(ra=ra*u.deg, dec=dec*u.deg, frame='icrs')
    pos_now = pos.transform_to(frame_now)
    ra_now = np.array( [float(x.to_string(unit=u.deg, decimal=True)) 
                        for x in pos_now.ra] )
    dec_now = np.array( [float(x.to_string(unit=u.deg, decimal=True)) 
                         for x in pos_now.dec] )
    
    # Do the coordinate conversion now (input in degrees)
    za_az_eq = [eq_to_altaz(ra_now, dec_now, l, latitude=-30.7215, za=True) for l in lsts]
    za_az_eq = np.array(za_az_eq)
    eq_az = za_az_eq[:,1,:]
    eq_za = za_az_eq[:,0,:]
    
    # Apply periodicity to match astropy convention
    eq_az = np.mod(eq_az, 2.*np.pi)
    
    return astropy_az, astropy_za, eq_az, eq_za
    
