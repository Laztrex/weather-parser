import datetime
import locale
import logging

from termcolor import cprint
import unittest
from unittest.mock import patch, call

from weather_source.files.settings import APPID_WeatherOpenMap
from weather_source.source_api import WeatherMap
from weather_source.weather_maker import WeatherMaker


class NewDate(datetime.date):
    @classmethod
    def today(cls):
        return datetime.date(2020, 8, 6)


def mocked_requests_get(*args, **kwargs):
    class MockResponse:
        def __init__(self, json_data, status_code, text=None):
            self.json_data = json_data
            self.status_code = status_code
            self.text = text

        def json(self):
            return self.json_data

    if args[0] == 'http://api.openweathermap.org/data/2.5/weather':
        return MockResponse({'weather': [{'description': 'дождь'}], 'main': {'temp': 26.33}}, 200)
    elif args[0] == 'http://api.openweathermap.org/data/2.5/forecast':
        dicts = {'list': [{'main': {'temp': 25.92}, 'weather': [{'description': 'ясно'}], 'dt_txt': '2020-08-06 18:00:00'},
                          {'main': {'temp': 21.92}, 'weather': [{'description': 'ясно'}], 'dt_txt': '2020-08-06 21:00:00'}]}
        return MockResponse(dicts, 200)
    elif args[0] == 'http://api.openweathermap.org/data/2.5/find':
        return MockResponse({'list': [{'id': 524901, 'name': 'Moscow', 'coord': {'lat': 55.7522, 'lon': 37.6156}}]}, 200)
    elif args[0] == 'https://pogoda.mail.ru/prognoz/moskva/6-august/#2020':
        return MockResponse(json_data=None, status_code=200, text='тестируем')

    return MockResponse(None, 404)


class GlobalEngineTest(unittest.TestCase):

    TEST_FOR_ANALYZE_WEATHER = [(datetime.datetime(2020, 7, 30, 6, 0), '+20', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 9, 0), '+10', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 12, 0), '+18', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 15, 0), '+15', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 18, 0), '+20', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 21, 0), '+17', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 00, 0), '+25', 'ясно'),
                                (datetime.datetime(2020, 7, 30, 3, 0), '+16', 'ясно')]

    def setUp(self):
        logging.disable()
        cprint(f'Вызван {self.shortDescription()}', flush=True, color='cyan')
        self.today = datetime.datetime.now()

    def tearDown(self):
        cprint(f'Оттестировано. \n', flush=True, color='grey')

    @patch('weather_source.source_api.requests.get', side_effect=mocked_requests_get)
    @patch('weather_source.weather_maker.BeautifulSoup', return_value=None)
    @patch('weather_source.source_url.MailWeather.weather', return_value=['дождь', 'дождь', 'дождь', 'дождь'])
    @patch('weather_source.source_url.MailWeather.temp_weather', return_value=['+19', '+19', '+19', '+19'])
    @patch('logging.FileHandler')
    def test_run_api(self, mock_get, mock_bs, mock_temp, mock_weather, mock_log):
        """Тест получения погоды с API
        (используется метод weather_from_api)"""
        datetime.date = NewDate
        get_weather_test = \
            WeatherMaker(source=3, city='Москва', dates=['2020.08.06'],
                         command='push')
        get_weather_test.base_run(name_db='TEST')
        self.assertEqual(len(get_weather_test.data_weather), 1)
        self.assertEqual(len(get_weather_test.data_weather[datetime.date.today()]), 4)
        self.assertEqual(get_weather_test.data_weather[datetime.date.today()]['Утро'],
                         {'temp': '+19', 'weather': 'дождь'})
        self.assertEqual(get_weather_test.data_weather[datetime.date.today()]['Вечер'],
                         {'temp': '+24°', 'weather': 'ясно'})

    @patch('weather_source.source_api.requests.get', side_effect=mocked_requests_get)
    def test_get_weather_current(self, mock_get):
        """Тест получения текущей погоды с API
        (в программе не используется)"""
        locale.setlocale(locale.LC_ALL, '')
        get_weather_test = \
            WeatherMaker(source=3, city='Москва', dates=['2020.08.06'],
                         command='push')
        test_current_date = WeatherMap(get_weather_test, get_weather_test.city)
        test_current_date._check_city()
        self.assertEqual(test_current_date.current_weather(), {'weather:': 'дождь', 'temp': 26.33})
        self.assertIn(call('http://api.openweathermap.org/data/2.5/weather',
                           params={'id': 524901, 'units': 'metric', 'lang': 'ru',
                                   'APPID': APPID_WeatherOpenMap}), mock_get.call_args_list)

    def test_method_for_part_days(self):
        """Тест правильного распределения частей суток"""
        get_weather_test = \
            WeatherMaker(source=3, city='Москва', dates=['2020.08.06'],
                         command='push')
        test_method_for_part = WeatherMap(get_weather_test, get_weather_test.city)
        for data_weather in self.TEST_FOR_ANALYZE_WEATHER:
            test_method_for_part._method_for_part_days(data_weather)
        self.assertEqual(test_method_for_part.first_half_part, [20, 18, 20, 25])
        self.assertEqual(test_method_for_part.second_half_part, [10, 15, 17, 16])

    def test_analyze_parts(self):
        """Тест получения погоды недостающих частей суток"""
        # (0, (0, 0)), (1, (0, 15)), (2, (14, 16)), (3, (17, 18))
        get_weather_test = \
            WeatherMaker(source=3, city='Москва', dates=['2020.08.06'],
                         command='push')
        weather_check = ['пасмурно', 'ясно']
        test_method_for_part = WeatherMap(get_weather_test, get_weather_test.city)
        for part_day_imitation in [(0, (0, 0)), (1, (0, 0)), (2, (14, 16)), (3, (17, 18))]:
            test_method_for_part._analyze_parts(part_day_imitation, self.today.date(), weather_check)
        self.assertEqual(len(weather_check), 4)


if __name__ == '__main__':
    unittest.main()
