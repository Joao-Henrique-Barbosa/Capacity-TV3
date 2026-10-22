# -*- coding: utf-8 -*-
""" Módulo de predição de cobertura de radiodifusão.

Adaptador SuriaCov usado por scripts/prepare_environments.py. Os caminhos são
injetados pelo preparador via TV3_SURIACOV_CONFIG; configure paths.local.yaml,
sem editar caminhos neste módulo. A grade usada pela campanha cobre ±2°.

Authors:    Higo Thaian Pereira da Silva (higo.silva@redes.unb.br)

As atribuições do código original foram preservadas.
"""

# -----------------------------------------------------------------------------
# ---------------------------------- IMPORTS ----------------------------------
# -----------------------------------------------------------------------------
import os
import numpy as np
import matplotlib 
import matplotlib.pyplot as plt
import contextily as ctx
from PIL import Image
import geopandas as gpd
import geopy.distance
import rasterio
from rasterio.enums import Resampling
from tqdm import tqdm
from enum import IntEnum
from enum import auto
import math
import warnings
from pathlib import Path
from shapely.geometry import Point
import time
from ..third_party.py1812 import P1812
import logging
import yaml
import json
from scipy.interpolate import splev, splrep
from scipy.optimize import curve_fit
from skimage.draw import line
# -----------------------------------------------------------------------------
# ---------------------------------- Constantes -------------------------------
# -----------------------------------------------------------------------------

_GLB_ITU_LIMITS_FREQ_GHZ = [0.03,6]
_GLB_ITU_LIMITS_TX_HEIGHT = [1.0,3000.0]
_GLB_ITU_LIMITS_NUM_POINTS = 4
_GLB_MIN_ANT_GAIN_LIN = 0.0001
_GLB_MIN_ANT_GAIN_DBI = 10 * np.log10( _GLB_MIN_ANT_GAIN_LIN )
_GLB_BR_BOUNDING_BBOX = np.array([[-73.993,-28.8],[-33.8,5.3]])
_GLB_FIELD_TH_DICT = {
    'low_vhf': {
        'range': [ 54.0,88.0 ], # MHz
        'field_th': [ 58.0, 0.0 ] # dBmu
    },
    'high_vhf': {
        'range': [174.0, 216.0], # MHz
        'field_th': [ 64.0, 43.0 ] # dBmu
    },
    'low_uhf': {
        'range': [470.0, 608.0], # MHz
        'field_th': [ 70.0, 51.0 ] # dBmu
    },
    'high_uhf': {
        'range': [614.0, 698.0], # MHz
        'field_th': [ 70.0, 51.0 ] # dBmu
    },
    'fm_band': {
        'range': [76.0,108.0], # MHz
        'field_th': [ 66.0, 66.0 ] # dBmu
    }
}

_glb_kmpdg = (math.pi/180) * 6371
# -----------------------------------------------------------------------------
# ------------------------ CONFIGURAÇÃO ---------------------------------------
# -----------------------------------------------------------------------------

class SuriaCovConfig:
    """
    Class used to store configuration attributes.

    ...

    Attributes
    ----------
    config_data : dict
        Dictionary with data read from the configuration yaml.
    radio_zone_shp: 
        Shapefile used to calculate the radioclimatic zone.
    radio_zone_dict: 
        Dict used to calculate the radioclimatic zone.
    brazil_limits_shp:
        Shapefile with the territorial limits of Brazil.
    radio_zone_minx: double
        Minimum limit in longitude of the national territory.
    radio_zone_miny: double
        Minimum limit in latitude of the national territory.
    radio_zone_resol: double
        Resolution of the grid used in calculating the radioclimatic zone.
    clutter_ref_tif_path: str
        Path to reference tif file used in clutter processing.

    Methods
    -------
    _load_config( self, yaml_config_file: str ):
        Reads the yaml configuration file. 
    """
    def __init__(self, yaml_config_file='suriacov_config.yaml' ):

        self.config_data = []
        self.radio_zone_shp = []
        self.radio_zone_dict = {}
        self.brazil_limits_shp = []
        self.radio_zone_minx = []
        self.radio_zone_miny = []
        self.radio_zone_resol = []
        self.clutter_ref_tif_path = []
        self.output_files_dir = []
        self.brazil_tif_file = []
        self.tifs_files_dir = []
        self.default_tx_power_kw = None
        self.default_tx_polarization = None
        self.default_tx_polarization_id = None
        self.default_tx_height = None
        self.default_min_size_dg = None
        self.shadow_margin = None
        self._load_config( yaml_config_file )

    def _load_config( self, yaml_config_file: str ):
        '''Reads the yaml configuration file. 

        Parameters
        ----------
        yaml_config_file : str
            Caminho para o arquivo de configuração

        '''
        # Proccess paths auxiliary function
        def proccess_paths(d):
            for k, v in d.items():
                if isinstance(v, dict):
                    proccess_paths(v)
                else:
                    d[k] = str((Path(yaml_config_file).resolve().parent / v).resolve())
            return d

        # Carregar yaml de configuração
        config_path = str(Path(yaml_config_file).resolve())
        with open(config_path) as file:
            self.config_data = yaml.safe_load(file)

        # Processar caminhos dos arquivos
        self.config_data[ 'ProcfilePaths' ] = proccess_paths(self.config_data['filePaths'])

        script_path = os.path.realpath(__file__)
        # Pasta de saída de arquivos
        self.output_files_dir = os.path.join(script_path, self.config_data['filePaths']['output_data_folder'])
        # Pasta para armazenar os .tifs
        self.tifs_files_dir = os.path.join(script_path, self.config_data['filePaths']['tifs_data_folder'])

        # Criar pastas caso não existam
        if not os.path.exists(self.output_files_dir): 
            # if the demo_folder directory is not present  
            # then create it. 
            os.makedirs(self.output_files_dir)
            logging.debug(f'Pasta de arquivos de saída criada.')
        if not os.path.exists(self.tifs_files_dir): 
            # if the demo_folder directory is not present  
            # then create it. 
            os.makedirs(self.tifs_files_dir)
            logging.debug(f'Pasta dos arquivos .tif criada.')

        # Referente clutter tif file
        self.clutter_ref_tif_path = self.config_data[ 'ProcfilePaths' ][ 'ibgp' ][ 'clutter_ref_tif' ]
        # Arquivo tif global de referência
        self.brazil_tif_file = self.config_data[ 'ProcfilePaths' ][ 'srtm' ][ 'brazil_geotiff' ]

        # Pegar caminhos dos arquivos
        # SHP auxiliar para cálculo da zona radio climática
        self.radio_zone_shp = gpd.read_file( self.config_data[ 'ProcfilePaths' ][ 'ibge' ][ 'radio_zone_grid_shp' ] )
        self.radio_zone_dict = {}
        for index, row in self.radio_zone_shp.iterrows():
            i = row['i_id']
            j = row['j_id']
            self.radio_zone_dict[(i,j)] = row['zone']    

        # SHP de limites territoriais do brasil
        self.brazil_limits_shp = gpd.read_file( self.config_data[ 'ProcfilePaths' ][ 'ibge' ][ 'brazil_terr_limits_shp' ] )

        # Constantes
        # Limites da grade das zonas radio climáticas
        self.radio_zone_minx = self.config_data[ 'procConsts' ][ 'radio_zone_grid_minx' ]
        self.radio_zone_miny = self.config_data[ 'procConsts' ][ 'radio_zone_grid_miny' ]
        self.radio_zone_resol = self.config_data[ 'procConsts' ][ 'radio_zone_grid_resol' ]
        self.shadow_margin = self.config_data[ 'procConsts' ][ 'coverage_shadow_margin' ]

        # Valores padrão
        self.default_tx_power_kw = self.config_data[ 'defaultValues' ][ 'defaultTXPower' ]
        self.default_tx_polarization = self.config_data[ 'defaultValues' ][ 'defaultPolarization' ]
        self.default_tx_height = self.config_data[ 'defaultValues' ][ 'defaultTXHeight' ]
        self.default_tx_polarization_id = self.config_data[ 'defaultValues' ][ 'defaultPolarizationID' ]
        self.default_min_size_dg = self.config_data[ 'defaultValues' ][ 'defaultMinSize' ]
        
        return

# Carregar configuração
suriacov_config = SuriaCovConfig(os.environ["TV3_SURIACOV_CONFIG"])

# Arquivo de log
logging.basicConfig( level=logging.INFO, filename=str(Path(suriacov_config.output_files_dir) / "suriacov.log"), format="%(asctime)s - %(levelname)s - %(message)s")

# -----------------------------------------------------------------------------
# ---------------------------------- CLASSES ----------------------------------
# -----------------------------------------------------------------------------

class SuriaCovErrors(IntEnum):
    """ Classe de códigos dos erros de processamento do SuriaCov. """
    WARNING_DEFAULT_TX_POWER = 500
    WARNING_DEFAULT_TX_HEIGHT = auto()
    WARNING_DEFAULT_TX_ANTP = auto()
    WARNING_DEFAULT_TX_POL = auto()
    ERROR_EMPTY_FIELD = 700
    ERROR_NON_FLOAT_COORDS = auto()
    ERROR_TX_COORD_OUT_LIMITS = auto()
    ERROR_NEGATIVE_TX_POWER = auto()
    ERROR_NON_FLOAT_TX_POWER = auto()
    ERROR_NEGATIVE_TX_HEIGHT = auto()
    ERROR_NON_FLOAT_TX_HEIGHT = auto()
    ERROR_NON_FLOAT_FREQUENCY = auto()
    ERROR_INVALID_ANTP_FORMAT = auto()
    ERROR_INVALID_TX_POL = auto()
    ERROR_FREQ_OUT_LIMITS = auto()
    ERROR_POWER_OUT_LIMITS = auto()
    ERROR_POL_OUT_LIMITS = auto()
    ERROR_TXH_OUT_LIMITS = auto()
    COORD_OUT_BBOX = auto()
    ERROR_TXANT_LOWER = auto()


class SuriaCovStatus:

    _suriacov_error_message_dict = {
        SuriaCovErrors.WARNING_DEFAULT_TX_POWER: f'Valor da potência de transmissão configurado para o padrão ({suriacov_config.default_tx_power_kw} kW).',
        SuriaCovErrors.WARNING_DEFAULT_TX_HEIGHT: f'Valor da altura da antena transmissora configurado para o valor padrão ({suriacov_config.default_tx_height} m).',
        SuriaCovErrors.WARNING_DEFAULT_TX_ANTP: 'Padrão de radiação da antena transmissora configurado como isotrópico.',
        SuriaCovErrors.WARNING_DEFAULT_TX_POL: f'Polarização da antena transmissora configurada como {suriacov_config.default_tx_polarization}.',
        SuriaCovErrors.ERROR_EMPTY_FIELD: 'Campo de entrada ({aux_string}) vazio.',
        SuriaCovErrors.ERROR_NON_FLOAT_COORDS: 'Coordenadas de entrada não são do tipo float.',
        SuriaCovErrors.ERROR_TX_COORD_OUT_LIMITS: 'Coordenadas geográficas ({aux_string}) fora dos limites do território brasileiro.',
        SuriaCovErrors.ERROR_NEGATIVE_TX_POWER: 'Potência de transmissão possui valor negativo ({aux_string}).',
        SuriaCovErrors.ERROR_NON_FLOAT_TX_POWER: 'Valor da potência de transmissão ({aux_string}) não pode ser convertida para valor numérico.',
        SuriaCovErrors.ERROR_NEGATIVE_TX_HEIGHT: 'Altura da antena transmissora tem valor negativo ({aux_string}).',
        SuriaCovErrors.ERROR_INVALID_ANTP_FORMAT: 'Padrão de radiação da antena transmissora não está no padrão válido.',
        SuriaCovErrors.ERROR_NON_FLOAT_TX_HEIGHT: 'Valor da altura da antena transmissora ({aux_string}) não pode ser convertida para valor numérico.',
        SuriaCovErrors.ERROR_NON_FLOAT_FREQUENCY: 'Valor da frequência ({aux_string}) não pode ser convertido para valor numérico.',
        SuriaCovErrors.ERROR_INVALID_TX_POL: 'Polarização da antena transmissora inválida ({aux_string}).',
        SuriaCovErrors.ERROR_FREQ_OUT_LIMITS: 'Valor de frequência ({aux_string} GHz) fora dos limites entre 0,03 GHz a 6 GHz.',
        SuriaCovErrors.ERROR_POWER_OUT_LIMITS: 'Valor de potência de transmissão não permitido ({aux_string} kW).',
        SuriaCovErrors.ERROR_POL_OUT_LIMITS: 'Marcador de polarização inválido. Os valores permitidos são 1 (Horizontal) e 2 (Vertical).',
        SuriaCovErrors.ERROR_TXH_OUT_LIMITS: 'Altura do transmissor sob o solo está fora do limite permitido entre 1 m e 3000 m.',
        SuriaCovErrors.COORD_OUT_BBOX: 'Coordenada de entrada ({aux_string}) está fora dos limites da cena do ambiente.',
        SuriaCovErrors.ERROR_TXANT_LOWER: 'Valor máximo do padrão de radiação está abaixo de 1.0.'
    }

    def __init__(self, status_code: SuriaCovErrors, status_aux_string: str = ""):

        self.status_code = status_code
        error_message = (
            self._suriacov_error_message_dict[status_code]
            if not status_aux_string
            else self._suriacov_error_message_dict[status_code].format(
                aux_string=status_aux_string
            )
        )
        msg_type = 'Erro' if int( status_code ) >= 700 else 'Alerta'
        self.status_message = f'{msg_type} {int( status_code )}: {error_message}'

class SuriaCovExceptions(Exception):

    def __init__(self, message, error_code: SuriaCovErrors):
        super().__init__(message)
        self.error_code = error_code


def bresenham_line(start: tuple[int, int], end: tuple[int, int], line_type='aa') -> list[tuple[int, int]]:
    """Return a list of coordinates from `start` to `end` including both endpoints.

    This implementation is symmetrical. It uses the same set of coordinates in either direction.

    >>> bresenham_line((0, 0), (3, 4))
    [(0, 0), (1, 1), (1, 2), (2, 3), (3, 4)]
    >>> bresenham_line((3, 4), (0, 0))
    [(3, 4), (2, 3), (1, 2), (1, 1), (0, 0)]
    """
    # if line_type == 'aa':
    #     rr,cc,_ = line_aa(start[0], start[1], end[0], end[1])
    # else:
    #     rr,cc = line(start[0], start[1], end[0], end[1])
    rr,cc = line(start[0], start[1], end[0], end[1])
    points = list(zip(rr,cc))
    return points

def square_edges(top_left, l, n):
    top = np.stack(
        [np.linspace(top_left[0], top_left[0] + l, n//4 + 1),
         np.full(n//4 + 1, top_left[1])],
         axis=1
    )[:-1]
    left = np.stack(
        [np.full(n//4 + 1, top_left[0]),
         np.linspace(top_left[1], top_left[1] - l, n//4 + 1)],
         axis=1
    )[:-1]
    right = left.copy()
    right[:, 0] += l
    bottom = top.copy()
    bottom[:, 1] -= l
    return np.concatenate([top, right, bottom, left])

def compute_angular_distance( lat1: float, lon1: float, lat2: float, lon2: float ):

    lat1_rad = np.deg2rad( lat1 )
    lon1_rad = np.deg2rad( lon1 )
    lat2_rad = np.deg2rad( lat2 )
    lon2_rad = np.deg2rad( lon2 )

    arg_a = np.sin( lat1_rad ) * np.sin( lat2_rad )
    arg_b = np.cos( lat1_rad ) * np.cos( lat2_rad ) * np.cos( lon1_rad - lon2_rad )
    ang_dist = np.arccos( arg_a + arg_b )

    return ang_dist

class PropEnvironment:
    """
    Class to store and process environment related data.

    ...

    Attributes
    ----------
    tif_file_path : str
        Path to the .tif file with the propagation environment relief.
    raster_data : array
        
    data_array : array
        Matrix with the terrain elevation profile.
    env_epsg : str
        EPSG code of the geographic data reference system.
    xdim : float
        Number of pixels in the longitude domain.
    ydim : float
        Number of pixels in the latitude domain.
    xres : float
        Spatial resolution (in decimal) in the longitude domain.
    yres : float
        Spatial resolution (in decimal) in the latitude domain.
    bounding_box : array
        Bounding box of the scene in the following order: upper left long, upper left lat, lower left long, lower left lat.
    zone_map : array
        Array with the description of the radio-climatic zone of each pixel.
    downsample_rate : int
        Pixel grid downsample rate.

    Methods
    -------
    coord_to_index(self, lon_coord: float, lat_coord: float):
        Convert a pair of coordinates (expressed in decimals) to a pair of indices in the environment grid.
    index_to_coord(self, i_c: int, j_c: int):
        Convert a pair of indices to a pair of coordinates in the environment grid.
    get_distance_map(self, tx_lon: float, tx_lat: float):
        Compute the tx-rx distance map expressed in km.
    get_los_map(self, tx_coord, tx_height, rx_height):
        Compute the line-of-sight condition map.
    """

    # Dicionários de classificação para diferentes tipos de subset
    env_classes = {
        'LC_Type1': {
            1: 'Evergreen Needleleaf Forests',
            2: 'Evergreen Broadleaf Forests',
            3: 'Deciduous Needleleaf Forests',
            4: 'Deciduous Broadleaf Forests',
            5: 'Mixed Forests',
            6: 'Closed Shrublands',
            7: 'Open Shrublands',
            8: 'Woody Savannas',
            9: 'Savannas',
            10: 'Grasslands',
            11: 'Permanent Wetlands',
            12: 'Croplands',
            13: 'Urban and Built-up Lands',
            14: 'Cropland/Natural Vegetation Mosaics',
            15: 'Permanent Snow and Ice',
            16: 'Barren',
            17: 'Water Bodies',
            255: 'Unclassified'
        },
    }

    # Dicionário de mapeamento com base na sugestão fornecida
    lc2itu_map = {
        'Evergreen Needleleaf Forests': 'Urban/trees/forest', # Mapeado para "Urban/trees/forest" com uma altura de clutter de 15 metros.
        'Evergreen Broadleaf Forests': 'Urban/trees/forest', # Mapeado para "Urban/trees/forest" com uma altura de clutter de 15 metros.
        'Deciduous Needleleaf Forests': 'Urban/trees/forest', # Mapeado para "Urban/trees/forest" com uma altura de clutter de 15 metros.
        'Deciduous Broadleaf Forests': 'Urban/trees/forest', # Mapeado para "Urban/trees/forest" com uma altura de clutter de 15 metros.
        'Mixed Forests': 'Urban/trees/forest', # Mapeado para "Urban/trees/forest" com uma altura de clutter de 15 metros.
        'Closed Shrublands': 'Suburban', # Mapeados como "Suburban" por menos densas do que as florestas.
        'Open Shrublands': 'Suburban', # Mapeados como "Suburban" por menos densas do que as florestas.
        'Woody Savannas': 'Open/rural', # Mapeadas como "Open/rural" pois geralmente tem árvores esparsas ou são áreas abertas.
        'Savannas': 'Open/rural', # Mapeadas como "Open/rural" pois geralmente tem árvores esparsas ou são áreas abertas.
        'Grasslands': 'Open/rural', # Mapeadas como "Open/rural" pois geralmente tem árvores esparsas ou são áreas abertas.
        'Permanent Wetlands': 'Water/sea', # Mapeadas como "Water/sea", mas pode ser "Open/rural"
        'Croplands': 'Open/rural', # Considerados como "Open/rural"
        'Urban and Built-up Lands': 'Dense urban', # Considerados com "Dense urban"
        'Cropland/Natural Vegetation Mosaics': 'Open/rural', # Considerados como "Open/rural"
        'Permanent Snow and Ice': 'Water/sea',
        'Barren': 'Water/sea', # Sem altura e sem vegetação, considerados como "Water/sea"
        'Water Bodies': 'Water/sea', # Sem altura e sem vegetação, considerados como "Water/sea"
        'Unclassified': 'Unclassified'   # A ser decidido ou omitido
    }

    # Alturas de clutter representativas para cada categoria de clutter
    itu_clutter_codes_h = { #Nome, Código utilizado pra simulação, altura do clutter
        'Water/sea': (1, 0),
        'Open/rural': (2, 0),
        'Suburban': (3, 10),
        'Urban/trees/forest': (4, 15),
        'Dense urban': (5, 20),
    }

    def __init__(self, center_lon: float, center_lat: float, lateral_size_dg: float, num_samples: int = 360) -> None:

        self.data_array = None
        self.transformer = None
        self.meta = None
        self.env_epsg = None
        self.xdim = None
        self.ydim = None
        self.xres = None
        self.yres = None
        self.center_lat = center_lat
        self.center_lon = center_lon
        self.lateral_size_dg = lateral_size_dg
        self.num_samples = num_samples
        self.bounding_box = None
        self.zones_map = None
        self.clutter_map = None
        self.clutter_hmap = None
        self.processed = False

    def _get_zone_map(self):
        """Get the radio-climatic zones map based on the predefined zones dict '_glb_zones_grid_dict'.

        Returns
        -------
        zone : array
            Zones map.
        """
        zone = np.zeros_like(self.data_array)
        # Sweep region
        for x in range(self.data_array.shape[1]):
            for y in range(self.data_array.shape[0]):

                # Position
                coord_x, coord_y = self.index_to_coord( x, y )

                # Axis reference
                # prod_x = -1 if coord_x > 0.0 else 1
                # prod_y = -1 if coord_y < 0.0 else 1
                # Position index
                # i_id = prod_x * round( ( coord_x - suriacov_config.radio_zone_minx ) / suriacov_config.radio_zone_resol )
                # j_id = prod_y * round( ( coord_y - suriacov_config.radio_zone_miny ) / suriacov_config.radio_zone_resol )
                i_id = round( ( coord_x - suriacov_config.radio_zone_minx ) / suriacov_config.radio_zone_resol )
                j_id = round( ( suriacov_config.radio_zone_miny - coord_y ) / suriacov_config.radio_zone_resol )

                i_id = 0 if i_id < 0 else i_id
                j_id = 0 if j_id < 0 else j_id

                zone[y,x] = suriacov_config.radio_zone_dict[(i_id,j_id)]
                
        return zone

    def _classify_env_clutter( self, sub_set_type='LC_Type1' ):

        logging.debug(f'Clutter classification started.')
        start_t = time.time()

        # Open reference geotiff
        dataset = []
        try:
            # Open ref tif
            dataset = rasterio.open( suriacov_config.clutter_ref_tif_path )
        except Exception as excep:
            # Caso não seja possível carregar
            logging.error("Unable to load .tif file:", excep)

        # Band which contains the classification
        band = dataset.read(1)

        clutter_map = np.zeros_like(self.data_array)
        clutter_h_map = np.zeros_like(self.data_array)
        for x in range(self.data_array.shape[1]):
            for y in range(self.data_array.shape[0]):

                # Convert to coordinates
                rx_coord = self.index_to_coord(x,y)
                # Convert to indices in the reference tif
                py, px = dataset.index(rx_coord[0], rx_coord[1])
                # px, py = rasterio.transform.rowcol( dataset.transform, xs=rx_coord[0], ys=rx_coord[1])
                px, py = int(px), int(py)

                # Coordinate clutter class
                coord_class = band[py, px]
                if coord_class is not None:
                    class_cod = coord_class
                    # LC_TYPE_1 Class name
                    lc_type_1_class_name = self.env_classes[sub_set_type][class_cod]
                    # Corresponding ITU class
                    itu_class = self.lc2itu_map[lc_type_1_class_name]
                    # ITU class code
                    itu_class_code = self.itu_clutter_codes_h[itu_class][0]
                    # ITU clutter height
                    itu_class_height = self.itu_clutter_codes_h[itu_class][1]

                    # Pass to the maps
                    clutter_map[y,x] = itu_class_code
                    clutter_h_map[y,x] = itu_class_height
        # Close data set
        dataset.close()

        end_t = time.time()
        logging.debug(f'Clutter classification completed ({end_t - start_t} s).')

        return clutter_map, clutter_h_map

    def window_from_extent(self, xmin, xmax, ymin, ymax, aff):
        col_start, row_start = ~aff * (xmin, ymax)
        col_stop, row_stop = ~aff * (xmax, ymin)
        return ((int(row_start), int(row_stop)), (int(col_start), int(col_stop)))

    def process_env(self):
        # Carregar o arquivo tif
        try:

            xmin = self.center_lon - self.lateral_size_dg
            xmax = self.center_lon + self.lateral_size_dg
            ymin = self.center_lat - self.lateral_size_dg
            ymax = self.center_lat + self.lateral_size_dg

            with rasterio.open( suriacov_config.brazil_tif_file ) as raster_data:

                aff = raster_data.transform
                self.meta = raster_data.meta.copy()
                window = self.window_from_extent(xmin, xmax, ymin, ymax, aff)
                # Read croped array
                self.data_array = raster_data.read(1, window=window,
                    out_shape=(
                        raster_data.count,
                        self.num_samples,
                        self.num_samples
                    ),
                    resampling=Resampling.bilinear
                ).astype('float')
                # Update dataset metadata
                self.meta.update(height = window[0][1] - window[0][0],
                            width = window[1][1] - window[1][0],
                            affine = raster_data.window_transform(window))
                self.meta['affine'] = self.meta['affine'] * self.meta['affine'].scale(
                    (self.meta['width'] / self.data_array.shape[-1]),
                    (self.meta['height'] / self.data_array.shape[-2])
                )
                self.meta['width'] = self.data_array.shape[-1]
                self.meta['height'] = self.data_array.shape[-2]
                self.meta.pop('transform', None)
                # Transformer
                self.transformer = rasterio.transform.AffineTransformer(self.meta['affine'])

        except Exception as excep:
            # Caso não seja possível carregar
            logging.error("Unable to load .tif file:", excep)

        # Replace missing values with NaNs
        nodataval = self.meta['nodata']
        if np.any( self.data_array == nodataval ):
            self.data_array[self.data_array == nodataval] = 0.0

        # Get geographic information from the analysis region
        # Lateral dimensions (pixels)
        self.xdim = self.data_array.shape[0]
        self.ydim = self.data_array.shape[1]
        # EPSG
        self.env_epsg = self.meta['crs'].to_epsg()
        # Bounding box (coordinates)
        xres = self.meta['affine'][0]
        yres = self.meta['affine'][4]
        ulx, uly = self.transformer.xy( 0, 0 )
        lrx, lry = self.transformer.xy( self.xdim - 1, self.ydim - 1 )

        logging.debug(f'Dimensoes: {self.xdim},{self.ydim}')

        # Lateral resolutions
        self.xres = xres
        self.yres = yres
        self.bounding_box = np.array([ulx,uly,lrx,lry])

        # Get zones map
        self.zones_map = self._get_zone_map()
        # Get Clutter info
        clutter_map, clutter_hmap = self._classify_env_clutter()
        self.clutter_map = clutter_map
        self.clutter_hmap = clutter_hmap
        
        self.processed = True

        return self

    def coord_to_index(self, lon_coord: float, lat_coord: float):
        """Convert a pair of coordinates (expressed in decimals) to a pair of indices in the environment grid.

        Parameters
        ----------
        lon_coord : float
            Longitude coordinate in decimals.
        lat_coord : float
            Latitude coordinate in decimals.

        Returns
        -------
        i_id, j_id : tuple
            Tuple with the coordinates indices.

        Raises
        ------
        SuriaCovErrors.COORD_OUT_BBOX
            If coorinates are outside of the bounding box.
        """

        # if ( lon_coord > self.bounding_box[ 2 ] + 2.0 * self.xres ) or ( lon_coord < self.bounding_box[ 0 ] - 2.0 * self.xres ):
        #     warn_msg = f'Coordenada: {lon_coord}, Limites:[{ self.bounding_box[ 0 ] + 2.0 * self.xres }, { self.bounding_box[ 2 ] - 2.0 * self.xres }]'
        #     # Raise error
        #     error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=warn_msg )
        #     raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )

        # if ( lat_coord > self.bounding_box[ 1 ] + 2.0 * self.yres ) or ( lat_coord < self.bounding_box[ 3 ] - 2.0 * self.yres ):
        #     warn_msg = f'Coordenada: {lat_coord}, Limites:[{ self.bounding_box[ 1 ] + 2.0 * self.yres }, { self.bounding_box[ 3 ] - 2.0 * self.yres }]'
        #     # Raise error
        #     error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=warn_msg )
        #     raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )

        # Compute indices
        i_id = int( ( lon_coord - self.bounding_box[0] ) / self.xres )
        j_id = int( ( lat_coord - self.bounding_box[1] ) / self.yres )

        return i_id, j_id

    def index_to_coord(self, i_c: int, j_c: int):
        """Convert a pair of indices to a pair of coordinates in the environment grid.

        Parameters
        ----------
        i_c : int
            Longitude index.
        j_c : int
            Latitude index.

        Returns
        -------
        coord_x, coord_y : tuple
            Tuple with the coordinates indices.

        Raises
        ------
        SuriaCovErrors.COORD_OUT_BBOX
            If coorinates are outside of the bounding box.
        """

        if ( i_c > self.xdim ) or ( i_c < 0 ):
            # Raise error
            error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=str(i_c) )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )
        if ( j_c > self.ydim ) or ( j_c < 0 ):
            # Raise error
            error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=str(j_c) )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )

        # Position
        coord_x = self.bounding_box[0] + ( i_c * self.xres )
        coord_y = self.bounding_box[1] + ( j_c * self.yres )

        return coord_x, coord_y

    def get_distance_map(self, tx_lon: float, tx_lat: float):
        """Compute the tx-rx distance map expressed in km.

        Parameters
        ----------
        tx_lat : float
            Longitude transmitter coordinate.
        tx_lon : float
            Latitude transmitter coordinate.

        Returns
        -------
        distance_map : array
            Matrix with the tx-rx distances.

        Raises
        ------
        SuriaCovErrors.COORD_OUT_BBOX
            If coorinates are outside of the bounding box.
        """
        if ( tx_lon > self.bounding_box[ 2 ] ) or ( tx_lon < self.bounding_box[ 0 ] ):
            # Raise error
            error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=str(tx_lon) )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )
        if ( tx_lat > self.bounding_box[ 1 ] ) or ( tx_lat < self.bounding_box[ 3 ] ):
            # Raise error
            error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=str(tx_lat) )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )

        distance_map = np.zeros_like(self.data_array)
        #with tqdm(total=self.data_array.shape[0] * self.data_array.shape[1], desc= 'Calculando mapa de distâncias') as pbar:
        for x in range(self.data_array.shape[1]):
            for y in range(self.data_array.shape[0]):

                rx_coord = self.index_to_coord(x,y)
                distance_map[y,x] = geopy.distance.great_circle( ( tx_lon, tx_lat ), rx_coord ).km
                #pbar.update(1)

        return distance_map

    def get_los_map(self, tx_coord, tx_height, rx_height):
        """Compute the line-of-sight condition map.

        Parameters
        ----------
        tx_coord : tuple
            Tuple with the transmitter coordinates (longitude, latitude).
        tx_height : float
            Transmitter height over terrain.
        rx_height : float
            Receiver height over terrain.

        Returns
        -------
        los_map : array
            Matrix with the line-of-sight conditions.

        Raises
        ------
        SuriaCovErrors.COORD_OUT_BBOX
            If coorinates are outside of the bounding box.
        """
        if ( tx_coord[0] > self.bounding_box[ 2 ] ) or ( tx_coord[0] < self.bounding_box[ 0 ] ):
            # Raise error
            error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=str(tx_coord[0]) )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )
        if ( tx_coord[1] > self.bounding_box[ 1 ] ) or ( tx_coord[1] < self.bounding_box[ 3 ] ):
            # Raise error
            error = SuriaCovStatus( SuriaCovErrors.COORD_OUT_BBOX, status_aux_string=str(tx_coord[0]) )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.COORD_OUT_BBOX )

        los_map = np.full(self.data_array.shape, True)
        tx_coord_ij = self.coord_to_index(tx_coord[0], tx_coord[1])
        # Sweep region
        #with tqdm(total=self.data_array.shape[1] * self.data_array.shape[0], desc= f'Calculando condições de visibilidade"') as pbar:
        for x in range(self.data_array.shape[1]):
            for y in range(self.data_array.shape[0]):

                # Heights over terrain
                tx_h_z = tx_height + self.data_array[tx_coord_ij[1],tx_coord_ij[0]]
                rx_h_z = rx_height + max(self.data_array[(y,x)], 0.0)
                h_diff = rx_h_z - tx_h_z

                # Bresenham line
                path_line = bresenham_line(tx_coord_ij, (x,y), line_type=0)
                # Search for visibility
                num_voxels = len(path_line)
                for i in range(num_voxels):
                    
                    los_height = h_diff * ( i / num_voxels ) + tx_h_z
                    if los_height < self.data_array[ (path_line[i][1],path_line[i][0]) ]:
                        los_map[y,x] = False
                        break
                
                #pbar.update(1)

        return los_map

    def __repr__(self):
        return f"PropEnvironment('{self.center_lon}', {self.center_lat}, {self.lateral_size_dg}, num_samples={self.num_samples})"

    def __str__(self):

        base_info = []
        base_info.append( f'Ambiente de propagação - Centro: ( {self.center_lon}°, {self.center_lat}° )' )
        base_info.append( f'\tESPG: {self.env_epsg}' )
        base_info.append( f'\tDimensoes: {self.xdim} x {self.ydim} (Pixels)' )
        base_info.append( f'\tLimites: [{self.bounding_box[0]}, {self.bounding_box[1]}, {self.bounding_box[2]}, {self.bounding_box[3]}]' )
        base_info.append( f'\tResolução: {self.xres} x {self.xres}' )

        return '\n'.join(base_info)

class Transmitter:

    """ Classe usada para armazenar informações referentes ao transmissor
    """

    _pol_id_dict = {
        1: 'Horizontal',
        2: 'Vertical'
    }

    def __init__(self,
                 tx_lat: float,
                 tx_lon: float,
                 freq_ghz: float,
                 tx_power_kw: float,
                 tx_polarization_id: int,
                 tx_height_ov_ground: float,
                 tx_ant_pattern: dict ) -> None:

        self.freq_ghz = self._get_freq(freq_ghz)
        self.tx_power_kw = self._get_power(tx_power_kw)
        self.tx_polarization_id = self._get_pol(tx_polarization_id)
        self.tx_height_ov_ground = self._get_height(tx_height_ov_ground)
        self.tx_ant_pattern = {}
        self.tx_ant_pattern_db = {}
        self.tx_coord = self._get_tx_coords(tx_lat, tx_lon)

        self._get_tx_ant_pattern( tx_ant_pattern )

    def _get_tx_coords(self, tx_lat: float, tx_lon: float):

        # Checar se a coordenada do transmissor está nos limites do território
        tx_coord_pt = Point( tx_lon, tx_lat )
        if not tx_coord_pt.within( suriacov_config.brazil_limits_shp.geometry[0]):
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_TX_COORD_OUT_LIMITS, status_aux_string=f'{tx_lon},{tx_lat}' )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.ERROR_TX_COORD_OUT_LIMITS )

        tx_coord = ( tx_lon, tx_lat )
        return tx_coord

    def _get_freq(self, freq_ghz: float):

        # Checar se o valor de frequência está nos limites permitidos
        if (freq_ghz > _GLB_ITU_LIMITS_FREQ_GHZ[1]) or (freq_ghz <_GLB_ITU_LIMITS_FREQ_GHZ[0]):
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_FREQ_OUT_LIMITS, status_aux_string=f'{freq_ghz}' )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.ERROR_FREQ_OUT_LIMITS )

        return freq_ghz
        
    def _get_power(self,tx_power_kw: float):

        # Checar se o valor da potência é positivo
        if tx_power_kw <= 0.0001:
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_POWER_OUT_LIMITS, status_aux_string=f'{tx_power_kw}' )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.ERROR_POWER_OUT_LIMITS )

        return tx_power_kw

    def _get_pol(self,tx_polarization_id: int):

        # Checar se o marcador da polarização está correto
        if tx_polarization_id not in [1,2]:
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_POL_OUT_LIMITS )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.ERROR_POL_OUT_LIMITS )

        return tx_polarization_id

    def _get_height(self,tx_height_ov_ground: float):

        # Checar se a altura do transmissor está adequada
        if (tx_height_ov_ground < _GLB_ITU_LIMITS_TX_HEIGHT[0]) or (tx_height_ov_ground > _GLB_ITU_LIMITS_TX_HEIGHT[1]):

            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_TXH_OUT_LIMITS )
            raise SuriaCovExceptions( error.status_message, SuriaCovErrors.ERROR_TXH_OUT_LIMITS )

        return tx_height_ov_ground

    def _get_tx_ant_pattern( self, tx_ant_pattern: dict ):

        if not bool( tx_ant_pattern ) or (all(v == 0 for v in tx_ant_pattern.values()) ):
            # Caso o padrão não for definido, aplica-se um padrão isotrópico
            warnings.warn( 'Padrão de radiação não definido. Assumindo antena isotrópica.' )
            # Azimuth range
            az_array = np.linspace( 0, 360.0, 1000 )
            for az in az_array:

                self.tx_ant_pattern[ az ] = 1.0
                self.tx_ant_pattern_db[ az ] = 0.0

        else:

            # Load the antenna pattern
            ant_pat = {}
            for az_str in tx_ant_pattern:
                ant_pat[ float( az_str ) ] = tx_ant_pattern[ az_str ]
            # Sort the pattern
            r = [ r for _, r in sorted(zip(ant_pat.keys(), ant_pat.values())) ]
            az = sorted( ant_pat.keys() )
            for i in range(len(r)):

                self.tx_ant_pattern[ az[i] ] = r[i] if r[i] > _GLB_MIN_ANT_GAIN_LIN else _GLB_MIN_ANT_GAIN_LIN
                self.tx_ant_pattern_db[ az[i] ] = 10 * math.log10( r[i] ) if r[i] > _GLB_MIN_ANT_GAIN_LIN else _GLB_MIN_ANT_GAIN_DBI

            # Interpolate
            x = list( self.tx_ant_pattern.keys() )
            y = list( self.tx_ant_pattern.values() )

            spl = splrep( x,y )
            xnew = np.linspace( min( x ), max( x ), 1000 )
            ynew = splev( xnew, spl )

            tx_ant_pattern_new = {}
            tx_ant_pattern_db_new = {}
            for n in range(len( xnew )):

                tx_ant_pattern_new[ xnew[ n ] ] = ynew[ n ] if ynew[ n ] > _GLB_MIN_ANT_GAIN_LIN else _GLB_MIN_ANT_GAIN_LIN
                tx_ant_pattern_db_new[ xnew[ n ] ] = 10 * math.log10( ynew[ n ] ) if ynew[ n ] > _GLB_MIN_ANT_GAIN_LIN else _GLB_MIN_ANT_GAIN_DBI

            self.tx_ant_pattern = tx_ant_pattern_new
            self.tx_ant_pattern_db = tx_ant_pattern_db_new

            if max( self.tx_ant_pattern, key=self.tx_ant_pattern.get) < 0.95: 
                # Chamar erro
                error = SuriaCovStatus( SuriaCovErrors.ERROR_TXANT_LOWER )
                raise SuriaCovExceptions( error.status_message, SuriaCovErrors.ERROR_TXANT_LOWER )

        return

    def get_ant_pattern_shape(self, max_rad: float):

        # Get the projection of the antenna pattern on the map
        ant_norm = max_rad / max(self.tx_ant_pattern.values())
        ant_x = []
        ant_y = []
        az = list(self.tx_ant_pattern.keys())
        ap = list(self.tx_ant_pattern.values())
        an_factor = math.pi / 180.0
        for i in range(len(self.tx_ant_pattern.values())):

            ant_x.append( ant_norm * ap[i] * math.cos( az[i] * an_factor ) + self.tx_coord[0] )
            ant_y.append( ant_norm * ap[i] * math.sin( az[i] * an_factor ) + self.tx_coord[1] )
            
        ant_x.append( ant_norm * ap[0] * math.cos( 360.0 * an_factor ) + self.tx_coord[0] )
        ant_y.append( ant_norm * ap[0] * math.sin( 360.0 * an_factor ) + self.tx_coord[1] )

        return ant_x, ant_y

    def __str__(self):

        base_info = []
        base_info.append( f'Coordenadas do transmissor: ({self.tx_coord[0]}, {self.tx_coord[1]})' )
        base_info.append( f'Frequência de operação: {self.freq_ghz} GHz' )
        base_info.append( f'ERP: {self.tx_power_kw} kW' )
        base_info.append( f'Polarização: {self._pol_id_dict[ self.tx_polarization_id ]}' )
        base_info.append( f'HCI: {self.tx_height_ov_ground} m' )

        desc_str = '\n'.join(base_info)
        return desc_str

class Coverage:

    """
    Class to store and process coverage related data.

    Attributes
    ----------
    tx : Transmitter
        `Transmitter` instance with transmitter data.
    env : PropEnvironment
        `PropEnvironment` instance with environment data.
    rx_height : float
        Receiver height over terrain (m).
    perc : float

    path_loss_map : array
        Path loss map (expressed in dB).
    field_intensity_map : array
        Field intensity map (expressed in dBmuV/m).
    los_map : array
        Line-of-sight conditions map.
    distance_map : array
        TX-RX map (expressed in km).

    """
    def __init__(self, tx: Transmitter, env: PropEnvironment, rx_height: float, perc: float, fi_th: float ) -> None:

        self.tx = tx
        self.env = env
        self.rx_height = rx_height
        self.perc = perc
        self.path_loss_map = None
        self.field_intensity_map = None
        self.covered_regions = None
        self.los_map = None
        self.distance_map = env.get_distance_map(self.tx.tx_coord[0], self.tx.tx_coord[1])
        self.fi_th = fi_th
        self.max_field_intensity = None
        self.max_cov_dist = None
        self.min_cov_dist = None
        self.max_cov_rad = None
        self.min_cov_rad = None
        self.dist_los = []
        self.dist_nlos = []
        self.pl_los = []
        self.pl_nlos = []
        self.pl_models = {}
        self.coverage_info = {}
        
    def _get_path_profiles( self, rx_coord ):

        # Get coord index
        i_tx, j_tx = self.env.coord_to_index( self.tx.tx_coord[0], self.tx.tx_coord[1] )
        # Bresenham line
        path_coords = bresenham_line((i_tx, j_tx), (rx_coord))

        # Number of points
        num_points = len(path_coords)
        # Height profile
        height_profile = np.zeros((num_points))
        # Distance profile
        distance_profile = np.zeros((num_points))
        # Zone profile
        zone_profile = np.zeros((num_points))
        # Clutter profile
        clutter_hprofile = np.zeros((num_points))
        clutter_cprofile = np.zeros((num_points))
        for i in range(num_points):
            # Height profile
            height_profile[i] = max( self.env.data_array[(path_coords[i][1],path_coords[i][0])], 0.0 )
            # Distance profile
            distance_profile[i] = self.distance_map[(path_coords[i][1],path_coords[i][0])]
            # Zone_profile
            zone_profile[i] = self.env.zones_map[(path_coords[i][1],path_coords[i][0])]
            # Clutter profile
            clutter_hprofile[i] = self.env.clutter_hmap[(path_coords[i][1],path_coords[i][0])]
            clutter_cprofile[i] = self.env.clutter_map[(path_coords[i][1],path_coords[i][0])]
        # Set first distance to zero
        distance_profile[0] = 0.0

        # Check if the distance profile is in ascending order
        if not all(distance_profile[i] <= distance_profile[i+1] for i in range(len(distance_profile) - 1)):
            # Reordening
            idx_sort = distance_profile.argsort()
            height_profile = height_profile[idx_sort]
            zone_profile = zone_profile[idx_sort]
            clutter_hprofile = clutter_hprofile[idx_sort]
            clutter_cprofile = clutter_cprofile[idx_sort]
            distance_profile = distance_profile[idx_sort]
            path_coords = [path_coords[j] for j in idx_sort]

        return height_profile, distance_profile, zone_profile, path_coords, clutter_hprofile, clutter_cprofile, num_points

    def _short_path_coverage(self, rx_coord_ij, ant_gain_db):
        """Calcule os perfis curtos pela distância do raster, em km."""
        tx_coord_ij = self.env.coord_to_index(*self.tx.tx_coord)
        x, y = rx_coord_ij
        d_km = float(self.distance_map[y, x])
        # O perfil da BS é zerado em _get_path_profiles. Use a resolução
        # efetiva do raster nesse pixel, evitando um enlace artificial de 1 m.
        if tuple(rx_coord_ij) == tuple(tx_coord_ij) or d_km <= 0:
            positive = self.distance_map[np.isfinite(self.distance_map) & (self.distance_map > 0)]
            if not positive.size:
                raise ValueError('O mapa precisa conter distancias positivas.')
            d_km = float(positive.min())
        if not math.isfinite(d_km):
            raise ValueError('Distancia nao finita no perfil curto.')
        loss = 32.44 + 20 * math.log10(max(d_km, 0.001)) + 20 * math.log10(self.tx.freq_ghz * 1000)
        # Mesma conversão entre perda e campo usada pelo P.1812 (GHz e kW).
        field = 199.36 + 20 * math.log10(self.tx.freq_ghz) + 10 * math.log10(self.tx.tx_power_kw) - loss + ant_gain_db
        return loss, field

    def compute_point_coverage( self, rx_coord_ij ):

        tx_coord_ij = self.env.coord_to_index(self.tx.tx_coord[0], self.tx.tx_coord[1])
        # Distance map
        if self.distance_map is None:
            self.distance_map = self.env.get_distance_map(self.tx.tx_coord[0], self.tx.tx_coord[1])

        ant_patt_num_points = len( self.tx.tx_ant_pattern.keys() )
        ant_patt_resol = max( self.tx.tx_ant_pattern.keys() ) / ant_patt_num_points

        # RX coord
        rx_coord = self.env.index_to_coord(rx_coord_ij[0],rx_coord_ij[1])
        # Profiles
        height_profile, distance_profile, zone_profile, path_coords, clutter_hprofile, clutter_cprofile, num_points = self._get_path_profiles( rx_coord_ij )
        # Azimuth angle
        az_angle = np.rad2deg( divmod( math.atan2( rx_coord[1] - self.tx.tx_coord[1], rx_coord[0] - self.tx.tx_coord[0] ), 2 * math.pi )[1] )
        # Path losses diff on path
        i_az = int( divmod( math.floor( az_angle / ant_patt_resol ), ant_patt_num_points - 1 )[1] )
        ant_gain_db = self.tx.tx_ant_pattern_db[ list(self.tx.tx_ant_pattern)[i_az] ]

        path_loss = -np.inf
        field_intensity = 0.0
        if num_points > _GLB_ITU_LIMITS_NUM_POINTS:
            # Compute the path loss and field intensity
            Lb, Ep = P1812.bt_loss( self.tx.freq_ghz, 
                                    self.perc, 
                                    distance_profile, 
                                    height_profile, 
                                    clutter_hprofile, 
                                    clutter_cprofile, 
                                    zone_profile, 
                                    self.tx.tx_height_ov_ground, 
                                    self.rx_height, 
                                    self.tx.tx_polarization_id, 
                                    self.tx.tx_coord[1], 
                                    rx_coord[1], 
                                    self.tx.tx_coord[0], 
                                    rx_coord[0],
                                    Ptx=self.tx.tx_power_kw )
            path_loss = Lb
            field_intensity = ant_gain_db + Ep
        else:
            path_loss, field_intensity = self._short_path_coverage(rx_coord_ij, ant_gain_db)
        
        return path_loss, field_intensity

    def compute_coverage( self, proj_name: str ):
        """
        Compute the path loss, field intensity and los condition maps.
        """

        pl_time = 0.0
        misc_time = 0.0

        tx_coord_ij = self.env.coord_to_index(self.tx.tx_coord[0], self.tx.tx_coord[1])
        # Allocate arrays
        path_loss = np.zeros_like(self.env.data_array)
        field_intensity = np.zeros_like(self.env.data_array)
        los_map = np.full(self.env.data_array.shape, True)
        # Distance map
        if self.distance_map is None:
            self.distance_map = self.env.get_distance_map(self.tx.tx_coord[0], self.tx.tx_coord[1])

        ant_patt_num_points = len( self.tx.tx_ant_pattern.keys() )
        ant_patt_resol = max( self.tx.tx_ant_pattern.keys() ) / ant_patt_num_points
        # Sweep region
        #with tqdm(total=self.env.data_array.shape[0] * self.env.data_array.shape[1], desc= f'Calculando cobertura "({proj_name})"') as pbar:
        for x in range(self.env.data_array.shape[1]):
            for y in range(self.env.data_array.shape[0]):

                start_time = time.time()
                # RX coord
                rx_coord = self.env.index_to_coord(x,y)
                # Profiles
                height_profile, distance_profile, zone_profile, path_coords, clutter_hprofile, clutter_cprofile, num_points = self._get_path_profiles( (x,y) )
                # Azimuth angle
                az_angle = np.rad2deg( divmod( math.atan2( rx_coord[1] - self.tx.tx_coord[1], rx_coord[0] - self.tx.tx_coord[0] ), 2 * math.pi )[1] )
                # Path losses diff on path
                i_az = int( divmod( math.floor( az_angle / ant_patt_resol ), ant_patt_num_points - 1 )[1] )
                ant_gain_db = self.tx.tx_ant_pattern_db[ list(self.tx.tx_ant_pattern)[i_az] ]

                # Heights over terrain
                tx_h_z = self.tx.tx_height_ov_ground + self.env.data_array[tx_coord_ij[1],tx_coord_ij[0]]
                rx_h_z = self.rx_height + max(self.env.data_array[(y,x)], 0.0)
                h_diff = rx_h_z - tx_h_z
                # Comput LoS Map
                for i in range(num_points):
                    
                    los_height = h_diff * ( i / num_points ) + tx_h_z
                    if los_height < self.env.data_array[ (path_coords[i][1],path_coords[i][0]) ]:
                        los_map[y,x] = False
                        break
                misc_time = misc_time + time.time() - start_time

                if num_points > _GLB_ITU_LIMITS_NUM_POINTS:

                    start_time = time.time()
                    # Compute the path loss and field intensity
                    Lb, Ep = P1812.bt_loss( self.tx.freq_ghz, 
                                            self.perc, 
                                            distance_profile, 
                                            height_profile, 
                                            clutter_hprofile, 
                                            clutter_cprofile, 
                                            zone_profile, 
                                            self.tx.tx_height_ov_ground, 
                                            self.rx_height, 
                                            self.tx.tx_polarization_id, 
                                            self.tx.tx_coord[1], 
                                            rx_coord[1], 
                                            self.tx.tx_coord[0], 
                                            rx_coord[0],
                                            Ptx=self.tx.tx_power_kw )
                    path_loss[y,x] = Lb
                    field_intensity[y,x] = ant_gain_db + Ep

                    pl_time = pl_time + time.time() - start_time
                    if los_map[y,x]:

                        self.dist_los.append( distance_profile[-1] )
                        self.pl_los.append( Lb )
                    else:
                        self.dist_nlos.append( distance_profile[-1] )
                        self.pl_nlos.append( Lb )
                else:
                    path_loss[y, x], field_intensity[y, x] = self._short_path_coverage((x, y), ant_gain_db)

                #pbar.update(1)

        self.path_loss_map = path_loss
        self.field_intensity_map = field_intensity
        self.los_map = los_map

        return

    def compute_critical_distance( self, rx_coord, ant_patt_resol, ant_patt_num_points, pl_exp=4.0, shd_std=9.0 ):

        dth = 10
        ant_gain_db = -40.0
        # Azimuth angle
        az_angle = np.rad2deg( divmod( math.atan2( rx_coord[1] - self.tx.tx_coord[1], rx_coord[0] - self.tx.tx_coord[0] ), 2 * math.pi )[1] )
        for th in range(-dth,dth):
            az_angle_p = az_angle + th
            if az_angle_p < 0.0: az_angle = 0.0
            if az_angle_p > 2 * math.pi: az_angle = 2 * math.pi

            i_az = int( divmod( math.floor( az_angle_p / ant_patt_resol ), ant_patt_num_points - 1 )[1] )
            ant_gain_db_p = self.tx.tx_ant_pattern_db[ list(self.tx.tx_ant_pattern)[i_az] ]
            if ant_gain_db < ant_gain_db_p:
                ant_gain_db = ant_gain_db_p

        # Threshold
        gamma = self.fi_th - 199.36 - 20 * np.log10( self.tx.freq_ghz ) - ant_gain_db - 10 * np.log10( self.tx.tx_power_kw )
        # Path loss at 1 km
        pl_1km = 20 * np.log10( self.tx.freq_ghz ) + 92.45 + shd_std
        # Critical distance
        critical_dist = 10 ** ( -( gamma + pl_1km ) / ( 10 * pl_exp ) )

        return critical_dist

    def get_ant_gain_xy( self, rx_coord, ant_patt_resol, ant_patt_num_points ):

        # Azimuth angle
        az_angle = np.rad2deg( divmod( math.atan2( rx_coord[1] - self.tx.tx_coord[1], rx_coord[0] - self.tx.tx_coord[0] ), 2 * math.pi )[1] )
        i_az = int( divmod( math.floor( az_angle / ant_patt_resol ), ant_patt_num_points - 1 )[1] )
        # Antenna pattern
        ant_gain_db = self.tx.tx_ant_pattern_db[ list(self.tx.tx_ant_pattern)[i_az] ]

        return ant_gain_db

    def compute_coverage_new( self, proj_name: str ):
        """
        Compute the path loss, field intensity and los condition maps.
        """

        tx_coord_ij = self.env.coord_to_index(self.tx.tx_coord[0], self.tx.tx_coord[1])
        # Allocate arrays
        path_loss = np.zeros_like(self.env.data_array)
        # field_intensity = np.zeros_like(self.env.data_array)
        field_intensity = np.full(self.env.data_array.shape, np.nan)
        # Line of sight condition map 
        los_map = self.env.get_los_map(self.tx.tx_coord, self.tx.tx_height_ov_ground, self.rx_height)
        # Distance map
        if self.distance_map is None:
            self.distance_map = self.env.get_distance_map(self.tx.tx_coord[0], self.tx.tx_coord[1])
        # Antenna pattern 
        ant_patt_num_points = len( self.tx.tx_ant_pattern.keys() )
        ant_patt_resol = max( self.tx.tx_ant_pattern.keys() ) / ant_patt_num_points

        # Scene edges
        map_edges = np.abs( square_edges((0,0), self.env.num_samples - 1, self.env.num_samples * 4) ).astype(int)

        #with tqdm(total=len(map_edges), desc= f'Calculando cobertura "({proj_name})"') as pbar:
        for ij_coords in map_edges:

            # Edge coordinates
            i = int( ij_coords[1] )
            j = int( ij_coords[0] )

            # RX coord
            edge_rx_coord = self.env.index_to_coord(j,i)
            # Profiles
            edge_height_profile, edge_distance_profile, edge_zone_profile, edge_path_coords, edge_clutter_hprofile, edge_clutter_cprofile, edge_num_points = self._get_path_profiles( (j,i) )
            # Critical distance
            crit_dist = self.compute_critical_distance( edge_rx_coord, ant_patt_resol, ant_patt_num_points )
            nlos_th_flag = False

            for i in range( _GLB_ITU_LIMITS_NUM_POINTS + 1, edge_num_points ):
                # Get intermediate points
                path_coords = edge_path_coords[ 0 : i ]
                x = path_coords[-1][1]
                y = path_coords[-1][0]

                # if ( nlos_th_flag == True ) and ( los_map[x,y] == False ):
                #     continue

                if np.isnan(field_intensity[x,y]):

                    rx_coord = self.env.index_to_coord(y,x)
                    # Antenna pattern
                    ant_gain_db = self.get_ant_gain_xy( (rx_coord[0],rx_coord[1]), ant_patt_resol, ant_patt_num_points )

                    # Get intermediate profiles
                    height_profile = edge_height_profile[ 0 : i ]
                    distance_profile = edge_distance_profile[ 0 : i ]
                    zone_profile = edge_zone_profile[ 0 : i ]
                    clutter_hprofile = edge_clutter_hprofile[ 0 : i ]
                    clutter_cprofile = edge_clutter_cprofile[ 0 : i ]

                    # Compute the path loss and field intensity
                    Lb, Ep = P1812.bt_loss( self.tx.freq_ghz, 
                                            self.perc, 
                                            distance_profile, 
                                            height_profile, 
                                            clutter_hprofile, 
                                            clutter_cprofile, 
                                            zone_profile, 
                                            self.tx.tx_height_ov_ground, 
                                            self.rx_height, 
                                            self.tx.tx_polarization_id, 
                                            self.tx.tx_coord[1], 
                                            rx_coord[1], 
                                            self.tx.tx_coord[0], 
                                            rx_coord[0],
                                            Ptx=self.tx.tx_power_kw )
                    path_loss[x,y] = Lb
                    field_intensity[x,y] = ant_gain_db + Ep

                    if ( field_intensity[x,y] < self.fi_th - 2 * suriacov_config.shadow_margin ) and ( los_map[x,y] == False ) and ( distance_profile[-1] > crit_dist ):
                        nlos_th_flag = True

            #pbar.update(1)

        # Fill the blank space in the vicinity of the tx with the maximum power
        for x_p in range(-_GLB_ITU_LIMITS_NUM_POINTS, _GLB_ITU_LIMITS_NUM_POINTS+1, 1):
            for y_p in range(-_GLB_ITU_LIMITS_NUM_POINTS, _GLB_ITU_LIMITS_NUM_POINTS+1, 1):

                x = tx_coord_ij[0] + x_p
                y = tx_coord_ij[1] + y_p
                path_loss[y,x] = path_loss.min()
                field_intensity[y,x] = field_intensity.max()

        self.path_loss_map = path_loss
        self.field_intensity_map = field_intensity
        self.los_map = los_map

        return


    def compute_coverage_zones( self, pl_th : float, fi_th : float, mov_avg_blocksize=5 ):

        # Alloc arrays
        az_angle = np.zeros(2 * (self.env.xdim + self.env.ydim))
        x_pl = np.zeros(2 * (self.env.xdim + self.env.ydim))
        y_pl = np.zeros(2 * (self.env.xdim + self.env.ydim))
        x_fi = np.zeros(2 * (self.env.xdim + self.env.ydim))
        y_fi = np.zeros(2 * (self.env.xdim + self.env.ydim))
        pl_contour = np.zeros(2 * (self.env.xdim + self.env.ydim))
        fi_contour = np.zeros(2 * (self.env.xdim + self.env.ydim))

        tx_coord_i = self.env.coord_to_index(self.tx.tx_coord[0], self.tx.tx_coord[1])
        # Sweep on lateral sides of the scene
        k = 0
        for x in [ 0, self.env.xdim - 1 ]:
            for y in range(0, self.env.data_array.shape[0]):

                # Azimuth angle
                az_angle[k] = math.atan2( y - tx_coord_i[1], x - tx_coord_i[0] )
                # Path line
                path_line = bresenham_line(tx_coord_i, (x,y))
                # Path losses diff on path
                pl_line = abs( np.array([self.path_loss_map[xy[1]][xy[0]] for xy in path_line]) - pl_th )
                i_pl = pl_line.argmin()
                # Field intensity on path
                fi_line = abs( np.array([self.field_intensity_map[xy[1]][xy[0]] for xy in path_line]) - fi_th )
                i_fi = fi_line.argmin()

                # Save positions
                x_pl[k] = path_line[i_pl][0]
                y_pl[k] = path_line[i_pl][1]
                pl_contour[k] = pl_line[i_pl]

                x_fi[k] = path_line[i_fi][0]
                y_fi[k] = path_line[i_fi][1]
                fi_contour[k] = fi_line[i_fi]

                k=k+1
        # Sweep on upper and lower sides of the scene
        for y in [ 0, self.env.ydim - 1 ]:
            for x in range(0, self.env.data_array.shape[1]):

                # Azimuth angle
                az_angle[k] = math.atan2( y - tx_coord_i[1], x - tx_coord_i[0] )
                # Path line
                path_line = bresenham_line(tx_coord_i, (x,y))
                # Path losses diff on path
                pl_line = abs( np.array([self.path_loss_map[xy[1]][xy[0]] for xy in path_line]) - pl_th )
                i_pl = pl_line.argmin()
                # Field intensity on path
                fi_line = abs( np.array([self.field_intensity_map[xy[1]][xy[0]] for xy in path_line]) - fi_th )
                i_fi = fi_line.argmin()

                # Save positions
                x_pl[k] = path_line[i_pl][0]
                y_pl[k] = path_line[i_pl][1]
                pl_contour[k] = pl_line[i_pl]

                x_fi[k] = path_line[i_fi][0]
                y_fi[k] = path_line[i_fi][1]
                fi_contour[k] = fi_line[i_fi]

                k=k+1

        # Sort positions related to their azimuth
        x_pl = [x for _, x in sorted(zip(az_angle, x_pl))]
        y_pl = [y for _, y in sorted(zip(az_angle, y_pl))]
        x_fi = [x for _, x in sorted(zip(az_angle, x_fi))]
        y_fi = [y for _, y in sorted(zip(az_angle, y_fi))]
        pl_contour = [p for _, p in sorted(zip(az_angle, pl_contour))]
        fi_contour = [f for _, f in sorted(zip(az_angle, fi_contour))]
        az_angle = sorted(az_angle)

        # Moving average filter to smooth
        x_pl = np.convolve(x_pl, np.ones(mov_avg_blocksize), "valid")/mov_avg_blocksize
        y_pl = np.convolve(y_pl, np.ones(mov_avg_blocksize), "valid")/mov_avg_blocksize
        x_fi = np.convolve(x_fi, np.ones(mov_avg_blocksize), "valid")/mov_avg_blocksize
        y_fi = np.convolve(y_fi, np.ones(mov_avg_blocksize), "valid")/mov_avg_blocksize

        # Convert the contour to coordinates
        pl_th_c = [self.env.index_to_coord(x_c,y_c) for x_c, y_c in zip(x_pl, y_pl)]
        fi_th_c = [self.env.index_to_coord(x_c,y_c) for x_c, y_c in zip(x_fi, y_fi)]
        x_pl_c = []
        y_pl_c = []
        for i in range(len(pl_th_c)):
            x_pl_c.append( pl_th_c[i][0] )
            y_pl_c.append( pl_th_c[i][1] )
        x_fi_c = []
        y_fi_c = []
        for i in range(len(fi_th_c)):
            x_fi_c.append( fi_th_c[i][0] )
            y_fi_c.append( fi_th_c[i][1] )

        return x_pl_c, y_pl_c, x_fi_c, y_fi_c, pl_contour, fi_contour, az_angle
            
    def get_outage_prob( self, fi_th: float, num_points : int = 50 ):

        # Distance axis
        dist_ax = np.linspace( 1.0, self.distance_map.max(), num_points )
        out_prob = np.zeros((num_points-1))

        for i in range( num_points - 1 ):

            field_circ = self.field_intensity_map[ (self.distance_map > dist_ax[i]) & (self.distance_map < dist_ax[i+1]) ]

            field_circ = field_circ[~np.isnan(field_circ)]
            field_circ = field_circ[~( field_circ == 0.0 )]

            if( len( field_circ ) > 0 ):
                out_prob[i] = len( field_circ[ field_circ < fi_th ] ) / len( field_circ )

        return out_prob, dist_ax[0:-1]

    def plot_field_coverage_map(self, figtitle: str, fi_th: float, pl_th: float, save_path: str, cmap='plasma', alpha=0.5):

        plt.rcParams["font.family"] = "serif"

        # Basemap -------------------------------------------------------------
        # Get the bounding box to plot the basemap
        west, south, east, north = (
            self.env.bounding_box[0], 
            self.env.bounding_box[3],
            self.env.bounding_box[2], 
            self.env.bounding_box[1])
        # Download the image based on the bounding box
        map_img, map_ext = ctx.bounds2img(
            west, south, east, north, ll=True, source=ctx.providers.OpenStreetMap.Mapnik
        )
        # Img aspect adjust
        aspect_ratio = (map_ext[2] - map_ext[0]) / (map_ext[3] - map_ext[1])
        fig_width = 10
        fig_height = fig_width / aspect_ratio
        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.grid(True)
        ax.tick_params(axis="both", which="major", labelsize=11)        
        # Convert the img to coordinates
        warped_img, warped_ext = ctx.warp_tiles(map_img, map_ext, "EPSG:4326")
        # Show the basemap img
        ax.imshow(warped_img, extent=warped_ext, interpolation="sinc")

        # Coverage map --------------------------------------------------------
        # Get coverage contours
        _, _, x_fi_c, y_fi_c, _, _, _ = self.compute_coverage_zones(pl_th, fi_th)
        # Find the points inside the coverage contour
        # List of contour points
        temp_list = []
        for a, b in zip(x_fi_c, y_fi_c):
            temp_list.append([a, b])
        # Contour polygon and path
        polygon = np.array(temp_list)
        path = matplotlib.path.Path(polygon)
        # Auxiliary coverage map
        aux_fimap = np.full( self.field_intensity_map.shape, np.nan )
        for iy, ix in np.ndindex(aux_fimap.shape):
            # Convert index to coord
            c = self.env.index_to_coord(ix,iy)
            # Check if the path contains the points
            if path.contains_points([c]):
                aux_fimap[iy,ix] = self.field_intensity_map[iy,ix]

        # Plot the coverage map
        plti = ax.imshow( aux_fimap, cmap=cmap, extent=[ self.env.bounding_box[0], self.env.bounding_box[2], self.env.bounding_box[3], self.env.bounding_box[1]], alpha=alpha)
        plt.colorbar(plti, fraction=0.036, pad=0.04 )
        # Plot the coverage contour
        plt.plot( x_fi_c,y_fi_c, color='yellow', label=f'Contorno de proteção para {fi_th} db\u03bcV/m', linewidth=1 )

        # Get the antenna radiation pattern
        ant_x, ant_y = self.tx.get_ant_pattern_shape(0.3)
        plt.plot(ant_x,ant_y,'-.',color='red', label='Padrão de radiação da antena transmissora')

        # Adição da legenda ao mapa
        lgd=ax.legend(loc="upper left",fontsize=10)

        # Plot transmitter coordinate
        ax.plot( self.tx.tx_coord[0], self.tx.tx_coord[1],'^',color='red',markersize=15)
        # Grid
        plt.grid(color='black', linestyle='-.', linewidth=0.6)
        # Figure title
        plt.title( figtitle, fontsize=15)

        # Save figure
        plt.savefig( save_path, format='png', dpi=300, bbox_inches='tight' )
        plt.close()

        return

    def get_reception_pattern_layer( self, fi_th: float, pl_th: float, save_path: str, cmap='plasma', alpha=0.5 ):

        # Get coverage contours
        _, _, x_fi_c, y_fi_c, _, _, _ = self.compute_coverage_zones(pl_th, fi_th)

        # Contour centered at TX
        contour_tx = np.vstack((x_fi_c, y_fi_c)).T - self.tx.tx_coord
        # Compute the norm
        contour_norm = np.linalg.norm(contour_tx, axis=1)
        # Max and Min coverage radii
        max_cov_rad = contour_norm.max()
        min_cov_rad = contour_norm.min()
        max_cov_id = contour_norm.argmax()
        min_cov_id = contour_norm.argmax()
        # Pixels IDs of the max and min points
        max_id_x, max_id_y = self.env.coord_to_index( x_fi_c[ max_cov_id ], y_fi_c[ max_cov_id ] )
        min_id_x, min_id_y = self.env.coord_to_index( x_fi_c[ min_cov_id ], y_fi_c[ min_cov_id ] )

        # Max and Min coverage radii in km
        max_cov_dist = self.distance_map[ max_id_y, max_id_x ]
        min_cov_dist = self.distance_map[ min_id_y, min_id_x ]

        # Circle countours
        az = np.linspace(0, 2 * np.pi, 100 )
        max_circ_x = max_cov_rad * np.cos( az ) + self.tx.tx_coord[0]
        max_circ_y = max_cov_rad * np.sin( az ) + self.tx.tx_coord[1]
        min_circ_x = min_cov_rad * np.cos( az ) + self.tx.tx_coord[0]
        min_circ_y = min_cov_rad * np.sin( az ) + self.tx.tx_coord[1]

        # Find the points inside the coverage contour
        # List of contour points
        temp_list = []
        for a, b in zip(x_fi_c, y_fi_c):
            temp_list.append([a, b])
        # Contour polygon and path
        polygon = np.array(temp_list)
        path = matplotlib.path.Path(polygon)
        # Auxiliary coverage map
        aux_fimap = np.full( self.field_intensity_map.shape, np.nan )
        for iy, ix in np.ndindex(aux_fimap.shape):
            # Convert index to coord
            c = self.env.index_to_coord(ix,iy)
            # Check if the path contains the points
            if path.contains_points([c]):
                aux_fimap[iy,ix] = self.field_intensity_map[iy,ix]

        # Plot the coverage map
        plt.figure(figsize=(15,11))
        plti = plt.imshow( aux_fimap, cmap=cmap, \
            extent=[ self.env.bounding_box[0], self.env.bounding_box[2], self.env.bounding_box[3], self.env.bounding_box[1]], alpha=alpha)
        # Plot coverage contours
        # Coverage contour
        plt.plot( x_fi_c, y_fi_c, color='green', linewidth=1.5 )
        # Max coverage contour
        plt.plot( max_circ_x, max_circ_y, '-.', color='red', linewidth=1.5 )
        # Min coverage contour
        plt.plot( min_circ_x, min_circ_y, '-.', color='blue', linewidth=1.5 )

        # Remove axis
        plt.axis('off')
        # Plot transmitter coordinate
        plt.plot( self.tx.tx_coord[0], self.tx.tx_coord[1],'^',color='red',markersize=15)
        # Save figure
        plt.savefig( save_path, format='png', dpi=300, bbox_inches='tight', transparent=True )
        plt.close()

        # Crop figure
        im = Image.open( save_path )
        im2 = im.crop(im.getbbox())
        im2.save( save_path )

        # Get coverage info
        self.max_cov_dist = max_cov_dist
        self.min_cov_dist = min_cov_dist
        self.max_cov_rad = max_cov_rad
        self.min_cov_rad = min_cov_rad
        self.fi_th = fi_th
        
        return

    def get_pl_models( self ):

        # define the true objective function
        def objective(x, a, b):
            return 10.0 * a * x + b

        if self.dist_los:

            # Get distance and pathloss
            dist_los = np.array( self.dist_los )
            pl_los = np.array( self.pl_los )
            # Sort arrays
            idx_sort_los = dist_los.argsort()
            pl_los = pl_los[ idx_sort_los ]
            dist_los = dist_los[ idx_sort_los ]

            # Get path loss parameters
            popt, _ = curve_fit(objective, np.log10( dist_los[2:] ), pl_los[2:] )
            # summarize the parameter values
            pl_exp_los, pl_offset_los = popt

            model_los = pl_offset_los + 10 * pl_exp_los * np.log10( dist_los )
            # Shadow fading std
            shadow_std = np.std( model_los - pl_los )

            self.pl_models[ 'los' ] = {}
            self.pl_models[ 'los' ][ 'exponent' ] = pl_exp_los
            self.pl_models[ 'los' ][ 'offset' ] = pl_offset_los
            self.pl_models[ 'los' ][ 'shadow_std' ] = shadow_std

        if self.dist_nlos:

            # Get distance and pathloss
            dist_nlos = np.array( self.dist_nlos )
            pl_nlos = np.array( self.pl_nlos )
            # Sort arrays
            idx_sort_nlos = dist_nlos.argsort()
            pl_nlos = pl_nlos[ idx_sort_nlos ]
            dist_nlos = dist_nlos[ idx_sort_nlos ]

            # Get path loss parameters
            popt, _ = curve_fit(objective, np.log10( dist_nlos[2:] ), pl_nlos[2:] )
            # summarize the parameter values
            pl_exp_nlos, pl_offset_nlos = popt

            model_nlos = pl_offset_nlos + 10 * pl_exp_nlos * np.log10( dist_nlos )
            # Shadow fading std
            shadow_std = np.std( model_nlos - pl_nlos )

            self.pl_models[ 'nlos' ] = {}
            self.pl_models[ 'nlos' ][ 'exponent' ] = pl_exp_nlos
            self.pl_models[ 'nlos' ][ 'offset' ] = pl_offset_nlos
            self.pl_models[ 'nlos' ][ 'shadow_std' ] = shadow_std

        return

    def get_covered_percentage_dist( self ):

        # Max and min distances
        d_min = self.distance_map.min()
        d_max = self.distance_map.max()

        # Number of covered pixels
        num_cov_px = len( self.field_intensity_map[ self.field_intensity_map > self.fi_th ] )
        perc = []
        dist = []
        for d in np.linspace( d_min, d_max, 100 ):

            dist.append(d)
            fi_f = self.field_intensity_map[ (self.distance_map < d) ]
            fi_f = fi_f[ ~np.isnan( fi_f ) ]
            perc.append( len( fi_f[ fi_f > self.fi_th ] ) / num_cov_px )

        dist = np.array( dist )
        perc = np.array( perc )

        return dist, perc

    def get_covered_percentage_reg( self, cov_percentage: float ):

        x = []
        y = []
        for i in range(self.env.data_array.shape[1]):
            for j in range(self.env.data_array.shape[0]):

                if self.field_intensity_map[i,j] > self.fi_th:

                    xp,yp = self.env.index_to_coord(i,j)
                    x.append(xp)
                    y.append(yp)
        x = np.array(x)
        y = np.array(y)
        x0, y0 = self.tx.tx_coord

        # compute radius
        r = np.sqrt((x - x0)**2 + (y - y0)**2)
        r0 = np.percentile(r, cov_percentage)

        return r0

    def get_covered_regions( self, fi_th: float, outage_prob: float = 0.5 ):
        '''
        Parameters
        ----------
        fi_th : float
            Limiar de intensidade de campo

        Returns
        -------

        Raises
        ------

        '''

        fi_array = np.copy( self.field_intensity_map )
        # Criar máscara booleana dos valores maiores que o limiar 
        fi_mask = np.zeros(fi_array.shape, dtype=bool)
        # False para os valores abaixo do limiar
        fi_mask[ fi_array > fi_th ] = True
        fi_mask[ fi_array <= fi_th ] = False
        
        fi_array[ fi_mask == False ] = np.nan

        # Coverage percentage per distance
        # dist, perc = self.get_covered_percentage_dist()
        # i_50 = np.abs( perc - 0.50 ).argmin()
        # i_95 = np.abs( perc - 0.95 ).argmin()

        # Raio de 95% de cobertura
        max_rad_dg = self.get_covered_percentage_reg(100)
        max_rad_km = max_rad_dg * _glb_kmpdg

        # Raio de 50% de cobertura
        rad_50p_dg = self.get_covered_percentage_reg(50)
        rad_50p = rad_50p_dg * _glb_kmpdg

        # Associar parâmetros
        self.max_cov_dist = max_rad_km
        self.max_cov_rad = max_rad_dg
        self.min_cov_dist = rad_50p
        self.min_cov_rad = rad_50p_dg
        self.max_field_intensity = fi_array[ ~np.isnan( fi_array ) ].max()

        # Retornar
        return fi_array, fi_mask

    def plot_covered_regions( self, covered_regions, covered_regions_mask, ls_dg: float, figtitle: str, save_path: str, with_base_map: bool = False, cmap: str = 'jet_r', alpha=1.0 ):

        if with_base_map:

            # Basemap ---------------------------------------------------------
            # Get the bounding box to plot the basemap
            west, south, east, north = (
                self.env.bounding_box[0], 
                self.env.bounding_box[3],
                self.env.bounding_box[2], 
                self.env.bounding_box[1])
            # Download the image based on the bounding box
            map_img, map_ext = ctx.bounds2img(
                west, south, east, north, ll=True, source=ctx.providers.OpenStreetMap.Mapnik
            )
            # Img aspect adjust
            aspect_ratio = (map_ext[2] - map_ext[0]) / (map_ext[3] - map_ext[1])
            fig_width = 10
            fig_height = fig_width / aspect_ratio
            fig, ax = plt.subplots(figsize=(fig_width, fig_height))
            ax.grid(True)
            ax.tick_params(axis="both", which="major", labelsize=11)        
            # Convert the img to coordinates
            warped_img, warped_ext = ctx.warp_tiles(map_img, map_ext, "EPSG:4326")
            # Show the basemap img
            ax.imshow(warped_img, extent=warped_ext, interpolation="sinc")            

            extent = [ self.env.bounding_box[0], self.env.bounding_box[2], self.env.bounding_box[3], self.env.bounding_box[1]]
            # Plot the coverage map
            plti = plt.imshow( covered_regions, cmap=cmap, extent=extent, alpha=alpha)
            plt.colorbar(plti, fraction=0.036, pad=0.04 )

            # Get the antenna radiation pattern
            ant_x, ant_y = self.tx.get_ant_pattern_shape(0.3 * ls_dg)
            plt.plot(ant_x,ant_y,'-.',color='blue', label='Padrão de radiação da antena transmissora')

            # Plotar contorno
            plt.contour(covered_regions_mask, [0.5], colors="cyan", linewidths=1, extent=extent, origin='image')

            # Adição da legenda ao mapa
            lgd=plt.legend(loc="upper left",fontsize=10)

            # Plot transmitter coordinate
            plt.plot( self.tx.tx_coord[0], self.tx.tx_coord[1],'^',color='red',markersize=15)

            if ( isinstance( self.max_cov_rad, float ) ) and ( isinstance( self.min_cov_rad, float ) ):

                # Circle countours
                az = np.linspace(0, 2 * np.pi, 100 )
                max_circ_x = self.max_cov_rad * np.cos( az ) + self.tx.tx_coord[0]
                max_circ_y = self.max_cov_rad * np.sin( az ) + self.tx.tx_coord[1]
                min_circ_x = self.min_cov_rad * np.cos( az ) + self.tx.tx_coord[0]
                min_circ_y = self.min_cov_rad * np.sin( az ) + self.tx.tx_coord[1]

                # Max coverage contour
                plt.plot( max_circ_x, max_circ_y, '-.', color='red' )
                # Min coverage contour
                plt.plot( min_circ_x, min_circ_y, '-.', color='green' )

            # Grid
            plt.grid(color='black', linestyle='-.', linewidth=0.6)
            # Figure title
            plt.title( figtitle, fontsize=15)

            # Save figure
            plt.savefig( save_path, format='png', dpi=300, bbox_inches='tight' )
            plt.close()

        else:

            extent = [ self.env.bounding_box[0], self.env.bounding_box[2], self.env.bounding_box[3], self.env.bounding_box[1]]
            # Plotar (...)
            plt.figure(figsize=(15,11))
            plti = plt.imshow( covered_regions, cmap=cmap,  alpha=alpha, extent=extent)
            
            # Plotar contorno
            plt.contour(covered_regions_mask, [0.5], colors="cyan", linewidths=1, extent=extent, origin='image')

            if ( isinstance( self.max_cov_rad, float ) ) and ( isinstance( self.min_cov_rad, float ) ):

                # Circle countours
                az = np.linspace(0, 2 * np.pi, 100 )
                max_circ_x = self.max_cov_rad * np.cos( az ) + self.tx.tx_coord[0]
                max_circ_y = self.max_cov_rad * np.sin( az ) + self.tx.tx_coord[1]
                min_circ_x = self.min_cov_rad * np.cos( az ) + self.tx.tx_coord[0]
                min_circ_y = self.min_cov_rad * np.sin( az ) + self.tx.tx_coord[1]

                # Max coverage contour
                plt.plot( max_circ_x, max_circ_y, '-.', color='red', linewidth=1.5 )
                # Min coverage contour
                plt.plot( min_circ_x, min_circ_y, '-.', color='green', linewidth=1.5 )

            # Get the antenna radiation pattern
            ant_x, ant_y = self.tx.get_ant_pattern_shape(0.3 * ls_dg)
            plt.plot(ant_x,ant_y,'-.',color='blue', label='Padrão de radiação da antena transmissora')

            # Remove axis
            plt.axis('off')
            # Plot transmitter coordinate
            plt.plot( self.tx.tx_coord[0], self.tx.tx_coord[1],'^',color='blue',markersize=20)

            # Save figure
            plt.savefig( save_path, format='png', dpi=300, bbox_inches='tight', transparent=True )
            plt.close()

        return

def get_map_tif_file( center_latitude: float, center_longitude: float, lateral_size_dg: float, proj_name: str ) -> str:
    '''Checks if the .tif file already exists, otherwise, downloads the file.

    Parameters
    ----------
    center_latitude : float
        Center latitude of the tif file (in decimal degrees).
    center_longitude : float
        Center longitude of the tif file (in decimal degrees).
    lateral_size_dg : float
        Lateral size of the tif map (in decimal degrees).
    proj_name : str
        Project name. Used as base of the output file name.

    Returns
    -------
    output_filename : str
        Output tif file path.
    '''
    
    map_folder = f"{suriacov_config.tifs_files_dir}/{proj_name}"
    if not os.path.exists(map_folder): 
        
        # if the demo_folder directory is not present  
        # then create it. 
        os.makedirs(map_folder) 

    # Define the output filename
    output_filename = f'{map_folder}/dem_center{center_latitude}_{center_longitude}_ls{lateral_size_dg:2.2}DG.tif'
    tif_file = Path(output_filename)
    # Checks if the .tif file already exists in the database
    if tif_file.is_file():
        logging.info(f'Arquivo tif ({output_filename}) do projeto {proj_name} já existe.')
        return output_filename
    # Else, download the file
    
    # Scene bounding box
    scene_bounds = ( center_longitude - lateral_size_dg,
                     center_latitude - lateral_size_dg,
                     center_longitude + lateral_size_dg,
                     center_latitude + lateral_size_dg )

    # Download the tif file
    try:
        command = f'eio clip -o {output_filename} --bounds {scene_bounds[0]} {scene_bounds[1]} {scene_bounds[2]} {scene_bounds[3]}'
        os.system(command)
    except Exception as excep:
        # Caso não seja possível carregar
        logging.info("Unable to download .tif file:", excep)

    return output_filename

def compute_app_scene_lateral_size( tx_power_kw: float, tx_ant_pattern_db: dict, field_th: float, path_loss_exp=4.0, resol=0.5 ):
    '''Calculates the lateral size of the analysis region approximately sufficient to capture all receivers covered by a given coverage threshold.
    The result is expressed in decimal degrees with a resolution of 0.5.

    Parameters
    ----------
    tx_power_kw : float
        Transmission power (in kW).
    freq_ghz : float
        Frequency (in GHz).
    field_th : float
        Field threshold (in dBmuV/m).
    path_loss_exp : float
        Reference path loss exponent for simplified computation (Default in 3.0).
    resol : float
        Resolution of the returned lateral size (Default in 0.5).

    Returns
    -------
        Lateral size of the scene expressed in decimal degrees.
    '''
    mean_tx_gain = np.mean(list((tx_ant_pattern_db.values())))
    d_th_log = ( 199.36 - 92.4 ) + 10.0 * np.log10( tx_power_kw ) + mean_tx_gain - field_th
    d_th = 10 ** ( d_th_log / ( ( path_loss_exp / 2 ) * 20 ) )
    # Distance in decimal degrees (minimum in 1.0)
    d_dg = ( divmod( d_th / _glb_kmpdg, resol )[0] + 1 ) * resol

    return d_dg

def compute_app_scene_lateral_size_new( tx: Transmitter, rx_height_ov_ground: float, excedance_perc: float, field_th: float, num_samples=360, resol=0.5, num_test_points=50 ):
    '''Calculates the lateral size of the analysis region approximately sufficient to capture all receivers covered by a given coverage threshold.
    The result is expressed in decimal degrees with a resolution of 0.5.

    Parameters
    ----------
    tx_power_kw : float
        Transmission power (in kW).
    freq_ghz : float
        Frequency (in GHz).
    field_th : float
        Field threshold (in dBmuV/m).
    path_loss_exp : float
        Reference path loss exponent for simplified computation (Default in 3.0).
    resol : float
        Resolution of the returned lateral size (Default in 0.5).

    Returns
    -------
        Lateral size of the scene expressed in decimal degrees.
    '''

    # Free space area
    path_loss_exp = 2.0
    mean_tx_gain = np.max(list((tx.tx_ant_pattern_db.values())))
    gamma = field_th - 199.36 - 20 * np.log10( tx.freq_ghz ) - mean_tx_gain - 10 * np.log10( tx.tx_power_kw )
    fspl_1km = 20 * np.log10( tx.freq_ghz ) + 92.45
    d_th = 10 ** ( -( gamma + fspl_1km ) / ( 10 * path_loss_exp ) )
    d_dg = round( d_th / _glb_kmpdg,1 )
    d_dg = min( 2.0, d_dg ) # Pad to a maximum of 2°

    if (( tx.tx_coord[0] - d_dg ) < _GLB_BR_BOUNDING_BBOX[0][0]):
        d_dg = np.abs( _GLB_BR_BOUNDING_BBOX[0][0] - tx.tx_coord[0] ) - 0.1
    if (( tx.tx_coord[0] + d_dg ) > _GLB_BR_BOUNDING_BBOX[0][1]):
        d_dg = np.abs( _GLB_BR_BOUNDING_BBOX[0][1] - tx.tx_coord[0] ) - 0.1
    if (( tx.tx_coord[1] - d_dg ) < _GLB_BR_BOUNDING_BBOX[1][0]):
        d_dg = np.abs( _GLB_BR_BOUNDING_BBOX[1][0] - tx.tx_coord[1] ) - 0.1
    if (( tx.tx_coord[1] + d_dg ) > _GLB_BR_BOUNDING_BBOX[1][1]):
        d_dg = np.abs( _GLB_BR_BOUNDING_BBOX[1][1] - tx.tx_coord[1] ) - 0.1

    # Create a test environment
    test_env = PropEnvironment( tx.tx_coord[0], tx.tx_coord[1], d_dg, num_samples=num_samples ).process_env()
    # TX coordinates
    tx_coord_ij = test_env.coord_to_index(tx.tx_coord[0], tx.tx_coord[1])
    # Test coverage
    test_coverage = Coverage(tx, test_env, rx_height_ov_ground, excedance_perc, field_th )

    # Distance (degrees) 
    dist_dg_list = []
    # Antenna pattern
    ant_patt_num_points = len( tx.tx_ant_pattern.keys() )
    ant_patt_resol = max( tx.tx_ant_pattern.keys() ) / ant_patt_num_points

    # Scene edges
    map_edges = np.abs( square_edges( (0,0), num_samples - 1, num_test_points ) ).astype(int)
    for ij_coords in map_edges:
         # Edge coordinates
        k = int( ij_coords[1] )
        j = int( ij_coords[0] )

        # Profiles
        edge_height_profile, edge_distance_profile, edge_zone_profile, edge_path_coords, edge_clutter_hprofile, edge_clutter_cprofile, edge_num_points = test_coverage._get_path_profiles( (j,k) )

        for i in range( edge_num_points, _GLB_ITU_LIMITS_NUM_POINTS + 1, -1 ):
            # Get intermediate points
            path_coords = edge_path_coords[ 0 : i ]
            x = path_coords[-1][1]
            y = path_coords[-1][0]

            rx_coord = test_coverage.env.index_to_coord(x,y)
            ant_gain_db = test_coverage.get_ant_gain_xy( (rx_coord[1],rx_coord[0]), ant_patt_resol, ant_patt_num_points )
            # Get intermediate profiles
            height_profile = edge_height_profile[ 0 : i ]
            distance_profile = edge_distance_profile[ 0 : i ]
            zone_profile = edge_zone_profile[ 0 : i ]
            clutter_hprofile = edge_clutter_hprofile[ 0 : i ]
            clutter_cprofile = edge_clutter_cprofile[ 0 : i ]

            # Compute the path loss and field intensity
            _, Ep = P1812.bt_loss( test_coverage.tx.freq_ghz, 
                                    test_coverage.perc, 
                                    distance_profile, 
                                    height_profile, 
                                    clutter_hprofile, 
                                    clutter_cprofile, 
                                    zone_profile, 
                                    test_coverage.tx.tx_height_ov_ground, 
                                    test_coverage.rx_height, 
                                    test_coverage.tx.tx_polarization_id, 
                                    test_coverage.tx.tx_coord[1], 
                                    rx_coord[1], 
                                    test_coverage.tx.tx_coord[0], 
                                    rx_coord[0],
                                    Ptx=test_coverage.tx.tx_power_kw )

            if ant_gain_db + Ep > field_th:

                rx_coord_dg = test_env.index_to_coord( x,y )
                # Distance in degrees
                dist_dg = np.rad2deg( compute_angular_distance( tx.tx_coord[0], tx.tx_coord[1], rx_coord_dg[0], rx_coord_dg[1] ) )
                # Append to the list
                dist_dg_list.append( dist_dg )
                break

    ls_dg_p = np.max( dist_dg_list ) if dist_dg_list else suriacov_config.default_min_size_dg
    ls_dg = max( np.ceil( ls_dg_p / resol ) * resol, resol )

    return ls_dg


def check_inputs( tx_latitude,
                tx_longitude,
                tx_power_kw,
                tx_height_ov_ground,
                tx_ant_patt,
                tx_polarization,
                frequency_ghz ):

    proc_inputs = {
        'tx_latitude': tx_latitude,
        'tx_longitude': tx_longitude,
        'tx_power_kw': tx_power_kw,
        'tx_height_ov_ground': tx_height_ov_ground,
        'tx_ant_patt': tx_ant_patt,
        'tx_polarization': tx_polarization,
        'frequency_ghz': frequency_ghz
    }

    # Flag para indicar se o processamento é válido. Só é inválida se uma 
    # entrada obrigatória não atende as especificações
    is_valid = True 
    # Lista de erros na checagem das entradas
    status_msg = []

    # Função auxiliar para checar se a variável é convertivel a float
    def is_float(element: any) -> bool:
        #If you expect None to be passed:
        if element is None: 
            return False
        try:
            float(element)
            return True
        except ValueError:
            return False
    # Função auxiliar para checar se uma string é convertível a json
    def is_json(element: any) -> bool:

        #If you expect None to be passed:
        if element is None: 
            return False
        try:
            if isinstance(element, str) or isinstance(element, dict):
                result = json.loads(element)
                if type(result) == dict:  return True
                else: return False
            return False
        except ValueError as e:
            return False
        
    # Checagem de coordenadas -------------------------------------------------
    # Checar se as coordenadas são float
    if ( not is_float(tx_latitude) ) or ( not is_float(tx_longitude) ):
        # Erro
        error = SuriaCovStatus( SuriaCovErrors.ERROR_NON_FLOAT_COORDS )
        status_msg.append( error.status_message )
        is_valid = False
    else:
        proc_inputs[ 'tx_latitude' ] = float( tx_latitude )
        proc_inputs[ 'tx_longitude' ] = float( tx_longitude )

        # Checar se a coordenada do transmissor está nos limites do território
        tx_coord_pt = Point( proc_inputs[ 'tx_longitude' ], proc_inputs[ 'tx_latitude' ] )
        if not tx_coord_pt.within( suriacov_config.brazil_limits_shp.geometry[0]):
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_TX_COORD_OUT_LIMITS, status_aux_string=f'{tx_longitude},{tx_latitude}' )
            status_msg.append( error.status_message )
            is_valid = False

    # Checagem da potência de transmissão -------------------------------------
    if not is_float( proc_inputs[ 'tx_power_kw' ] ):
        # Chamar erro
        error = SuriaCovStatus( SuriaCovErrors.ERROR_NON_FLOAT_TX_POWER, status_aux_string=f'{tx_power_kw}' )
        status_msg.append( error.status_message )
        # Usar valor padrão
        proc_inputs[ 'tx_power_kw' ] = suriacov_config.default_tx_power_kw
        warning = SuriaCovStatus( SuriaCovErrors.WARNING_DEFAULT_TX_POWER )
        status_msg.append( warning.status_message )
    else:
        proc_inputs[ 'tx_power_kw' ] = float( proc_inputs[ 'tx_power_kw' ] )

    # Checagem da altura da antena sob o solo ---------------------------------
    if not is_float( proc_inputs[ 'tx_height_ov_ground' ] ):
        # Chamar erro
        error = SuriaCovStatus( SuriaCovErrors.ERROR_NON_FLOAT_TX_HEIGHT, status_aux_string=f'{ tx_height_ov_ground }' )
        status_msg.append( error.status_message )
        # Usar valor padrão
        proc_inputs[ 'tx_height_ov_ground' ] = suriacov_config.default_tx_height
        warning = SuriaCovStatus( SuriaCovErrors.WARNING_DEFAULT_TX_HEIGHT )
        status_msg.append( warning.status_message )
    else:
        proc_inputs[ 'tx_height_ov_ground' ] = float( proc_inputs[ 'tx_height_ov_ground' ] )

    # Checagem do padrão de radiação ------------------------------------------
    if not is_json( proc_inputs[ 'tx_ant_patt' ] ):
        # Chamar erro
        error = SuriaCovStatus( SuriaCovErrors.ERROR_INVALID_ANTP_FORMAT )
        status_msg.append( error.status_message )
        # Calcular um padrão de radiação isotrópico
        proc_inputs[ 'tx_ant_patt' ] = {}
        # Azimuth range
        az_array = np.linspace( 0, 360.0, 360 )
        for az in az_array:
            proc_inputs[ 'tx_ant_patt' ][ str( az ) ] = 1.0
        warning = SuriaCovStatus( SuriaCovErrors.WARNING_DEFAULT_TX_ANTP )
        status_msg.append( warning.status_message )   
    else:
        # Carregar padrão de radiação
        proc_inputs[ 'tx_ant_patt' ] = json.loads( proc_inputs[ 'tx_ant_patt' ] )
        proc_inputs[ 'tx_ant_patt' ] = {k: v for k, v in proc_inputs[ 'tx_ant_patt' ].items() if v is not None}
        # Checar se o padrão de radiação é um dicionário e se é formado por pares str:float
        if not ( isinstance( proc_inputs[ 'tx_ant_patt' ], dict ) and all(isinstance(az, str) for az in proc_inputs[ 'tx_ant_patt' ].keys()) and
            all(isinstance(pt, float | int) for pt in proc_inputs[ 'tx_ant_patt' ].values()) ):
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_INVALID_ANTP_FORMAT )
            status_msg.append( error.status_message )
            # Calcular um padrão de radiação isotrópico
            proc_inputs[ 'tx_ant_patt' ] = {}
            # Azimuth range
            az_array = np.linspace( 0, 360.0, 360 )
            for az in az_array:
                proc_inputs[ 'tx_ant_patt' ][ str( az ) ] = 1.0
            warning = SuriaCovStatus( SuriaCovErrors.WARNING_DEFAULT_TX_ANTP )
            status_msg.append( warning.status_message )   

    # Checagem da polarização -------------------------------------------------
    # Checar se o tipo de polarização é válida
    if ( not bool( proc_inputs[ 'tx_polarization' ] ) ) or ( proc_inputs[ 'tx_polarization' ].lower() not in [ 'horizontal', 'vertical' ] ):
        # Chamar erro
        error = SuriaCovStatus( SuriaCovErrors.ERROR_INVALID_TX_POL, status_aux_string=f"{proc_inputs[ 'tx_polarization' ]}" )
        status_msg.append( error.status_message )
        # Usar o valor padrão
        proc_inputs['tx_polarization'] = suriacov_config.default_tx_polarization
        warning = SuriaCovStatus( SuriaCovErrors.WARNING_DEFAULT_TX_POL )
        status_msg.append( warning.status_message )   

    # Checagem da frequência --------------------------------------------------
    if isinstance( proc_inputs[ 'frequency_ghz' ], str ):
        proc_inputs[ 'frequency_ghz' ] = proc_inputs[ 'frequency_ghz' ].replace(',','.')
    if not is_float( proc_inputs[ 'frequency_ghz' ] ):
        # Chamar erro
        error = SuriaCovStatus( SuriaCovErrors.ERROR_NON_FLOAT_FREQUENCY, status_aux_string=f'{ frequency_ghz }' )
        status_msg.append( error.status_message )
        is_valid = False
    else:
        proc_inputs[ 'frequency_ghz' ] = float( proc_inputs[ 'frequency_ghz' ] ) / 1000.0
        # Checar se o valor de frequência está nos limites permitidos
        if (proc_inputs[ 'frequency_ghz' ] > _GLB_ITU_LIMITS_FREQ_GHZ[1]) or (proc_inputs[ 'frequency_ghz' ] <_GLB_ITU_LIMITS_FREQ_GHZ[0]):
            # Chamar erro
            error = SuriaCovStatus( SuriaCovErrors.ERROR_FREQ_OUT_LIMITS, status_aux_string=f"{ proc_inputs[ 'frequency_ghz' ] }" )
            status_msg.append( error.status_message )
            is_valid = False

    return is_valid, proc_inputs, status_msg


def get_pol_id( tx_polarization: str ):

    pol_ids_dict = {
        'horizontal': 1,
        'vertical': 2
    }

    pol_id = suriacov_config.default_tx_polarization_id
    if tx_polarization.lower() in pol_ids_dict:
        pol_id = pol_ids_dict[ tx_polarization.lower() ]

    return pol_id

def get_channel_coverage_specs( service_str: str, freq_ghz: float ):

    # Limiar de intensidade do campo
    fi_th = 0.0
    # Frequência em MHz
    freq_mhz = freq_ghz * 1000.0
    # Lista de serviços digitais
    digital_servs = [ 'RTVD', 'PBTVD', 'GTVD' ]
    # Lista de serviços de FM
    fm_servs = [ 'FM', 'RTRFM' ]

    channel_freq_band = ''
    is_digital = 0
    if service_str in fm_servs:
        channel_freq_band = 'fm_band'
        is_digital = 0
    else:
        # Caso não seja FM, calcular a banda e verificar se é digital
        for band, info in _GLB_FIELD_TH_DICT.items():

            if info['range'][0] <= freq_mhz <= info['range'][1]:
                channel_freq_band = band
                is_digital = 1 if service_str in digital_servs else 0
                break

    fi_th = _GLB_FIELD_TH_DICT[ channel_freq_band ][ 'field_th' ][ is_digital ]

    return fi_th, is_digital, channel_freq_band

def compute_coverage( proj_name: str,
                      tx_latitude: float,
                      tx_longitude: float,
                      tx_power_kw: float,
                      tx_height_ov_ground: float,
                      tx_ant_patt: dict,
                      tx_polarization_id: int,
                      frequency_ghz: float,
                      rx_height_ov_ground: float,
                      field_th: float,
                      excedance_perc: float=50,
                      num_samples=360 ):
    '''Calculates coverage for a given set of parameters that characterize the link.
    Parameters
    ----------
    proj_name : str
        Project name. The folders and files generated by the processing use this string in their names.
    tx_latitude : float
        Transmitter latitude (in decimal degrees).
    tx_longitude : float
        Transmitter longitude (in decimal degrees).
    tx_power_kw : float
        Transmitted power (in kW).
    tx_height_ov_ground : float
        Transmitter height over terrain.
    tx_ant_patt : dict
        Transmitter antenna pattern dictionary, with pairs azimuth: gain.
    tx_polarization : str
        Transmission polarization indicator. Should be 'Horizontal' or 'Vertical'.
    frequency_ghz : float
        Transmission frequency (in GHz).
    rx_height_ov_ground : float
        Receiver height over ground (in m).
    field_th : float
        Field threshold (in dBmuV/m).
    excedance_perc : float
        Excedance percentage of the field prediction (1 <= p <= 50 - Default in 50)
    num_sample : int
        Number of samples of the lateral size.

    Returns
    -------

    Raises
    ------

    '''

    logging.debug(f'Project {proj_name} started.')
    # Create the project outputs directory
    output_dir = f'{suriacov_config.output_files_dir}/{proj_name}'
    
    if not os.path.exists(output_dir) and suriacov_config.config_data['plot_coverage_maps']:
        # if the demo_folder directory is not present  
        # then create it. 
        logging.debug(f'Project output folder: {output_dir}.')
        os.makedirs(output_dir) 
        logging.debug(f'Pasta do projeto ("{output_dir}") criada.')

    # Create a Transmitter instance
    tx = Transmitter(
        tx_latitude,
        tx_longitude,
        frequency_ghz,
        tx_power_kw,
        tx_polarization_id,
        tx_height_ov_ground,
        tx_ant_patt )

    # Get a sufficient lateral size
    # ls_dg = compute_app_scene_lateral_size_new( tx, rx_height_ov_ground, excedance_perc, field_th, resol=0.1, num_samples=360 )
    ls_dg = 2
    logging.debug(f'Scene lateral size: {ls_dg} decimal degrees.')

    # Process the environment
    logging.debug(f'Propagation environment processing started.')
    start_t = time.time()
    env = PropEnvironment( tx_longitude, tx_latitude, ls_dg, num_samples=num_samples ).process_env()
    end_t = time.time()
    logging.debug(f'Propagation environment processed ({end_t - start_t} s).')

    # Process the coverage
    logging.debug(f'Coverage processing started.')
    start_t = time.time()
    coverage_data = Coverage(tx, env, rx_height_ov_ground, excedance_perc, field_th )
    coverage_data.compute_coverage(proj_name)
    end_t = time.time()
    logging.debug(f'Coverage processing completed ({end_t - start_t} s).')

    # Calcular região coberta
    cov_regions, cov_mask = coverage_data.get_covered_regions( field_th )
    if suriacov_config.config_data['plot_coverage_maps']:
        # Plot coverage maps
        logging.debug(f'Coverage map plot started.')
        start_t = time.time()

        # Figures names
        cov_regions_bmap_fig_path = f'{output_dir}/covered_regions_bmap_fith_{field_th}.png'
        cov_regions_fig_path = f'{output_dir}/covered_regions_fith_{field_th}.png'
        # Plot covered regions
        coverage_data.plot_covered_regions( cov_regions, cov_mask, ls_dg, f'Mapa de Cobertura - {proj_name}', cov_regions_bmap_fig_path, with_base_map=True, alpha=0.8 )
        coverage_data.plot_covered_regions( cov_regions, cov_mask, ls_dg, '', cov_regions_fig_path, with_base_map=False, alpha=1.0 )

        end_t = time.time()
        logging.debug(f'Coverage map plot completed ({end_t - start_t} s).')

    return tx, env, coverage_data



