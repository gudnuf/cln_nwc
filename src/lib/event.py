"""
Defines classes for handling events
"""

import hashlib
import time
import json
from coincurve import PrivateKey

# copied EventTags exactly from
# https://github.com/monty888/monstr/blob/cb728f1710dc47c8289ab0994f15c24e844cebc4/src/monstr/event/event.py


class EventTags:
    """
        split out so we can use event tags without have to create the whole event
    """

    def __init__(self, tags):
        self.tags = tags

    @property
    def tags(self):
        "access the tags property"
        return self._tags

    @tags.setter
    def tags(self, tags):
        # if passed in as json str e.g. as event is received over ws
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = None

        if tags is None:
            tags = []
        self._tags = tags

    def get_tags(self, tag_name: str):
        """
        returns tag data for tag_name, no checks on the data
        e.g. that #e, event id is long enough to be valid event
        :param tag_name:
        :return:
        """
        return [t[1:] for t in self._tags if len(t) >= 1 and t[0] == tag_name]

    def get_tags_value(self, tag_name: str) -> []:
        """
        returns [] containing the 1st value field for a given tag, in many cases this is all we want
        if not use get_tags
        :param tag_name:
        :return:
        """
        return [t[0] for t in self.get_tags(tag_name)]

    def get_tag_value_pos(self, tag_name: str, pos: int = 0,
                          default: str = None) -> str:
        """
            returns tag value (first el after tag name) for given tag_name at pos,
            if there isn't a tag at that pos then default is returned

            e.g. we only want very first d tags value else ''
                get_tag_value_pos('d', default='')

        """
        ret = default
        vals = self.get_tags_value(tag_name)
        if vals:
            ret = vals[pos]
        return ret

    @property
    def tag_names(self) -> set:
        # return all unique tag names
        return {c_tag[0] for c_tag in self._tags if len(c_tag) > 0}

    @property
    def e_tags(self):
        """
        :return: all ref'd events/#e tag in [evt_id, evt_id,...] makes sure evt_id is correct len
        """
        return [t[0] for t in self.get_tags('e') if len(t[0]) == 64]

    @property
    def p_tags(self):
        """
        :return: all ref'd profile/#p tag in [pub_k, pub_k,...] makes sure pub_k is correct len
        """
        return [t[0] for t in self.get_tags('p') if len(t[0]) == 64]

    def __str__(self):
        return json.dumps(self._tags)

    def __len__(self):
        return len(self._tags)

    def __getitem__(self, item):
        return self._tags[item]

    def __iter__(self):
        for c_tag in self._tags:
            yield c_tag

# copied some + adapted to use coincurve from
# https://github.com/monty888/monstr/blob/cb728f1710dc47c8289ab0994f15c24e844cebc4/src/monstr/event/event.py


class Event:
    @staticmethod
    def from_JSON(evt_json):
        """
        TODO: add option to verify sig/eror if invalid?
        creates an event object from json - at the moment this must be a full event, has id and has been signed,
        may add option for presigned event in future
        :param evt_json: json to create the event, as you'd recieve from subscription
        :return:
        """
        return Event(
            id=evt_json['id'],
            sig=evt_json['sig'],
            kind=evt_json['kind'],
            content=evt_json['content'],
            tags=evt_json['tags'],
            pub_key=evt_json['pubkey'],
            created_at=evt_json['created_at']
        )

    def __init__(self, id=None, sig=None, kind=None, content=None,
                 tags=None, pub_key=None, created_at=None):
        self._id = id
        self._sig = sig
        self._kind = kind
        self._created_at = created_at
        # normally the case when creating a new event
        if created_at is None:
            self._created_at = int(time.time())

        # content forced to str
        self._content = str(content)

        self._pub_key = pub_key

        self._tags = EventTags(tags)

    def serialize(self):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
        """
        if self._pub_key is None:
            raise Exception(
                'Event::serialize can\'t be done unless pub key is set')

        ret = json.dumps([
            0,
            self._pub_key,
            self._created_at,
            self._kind,
            self._tags.tags,
            self._content
        ], separators=(',', ':'), ensure_ascii=False)

        return ret

    def _get_id(self):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
            pub key must be set to generate the id
        """
        evt_str = self.serialize()
        self._id = hashlib.sha256(evt_str.encode('utf-8')).hexdigest()

    def sign(self, priv_key: str):
        """
            see https://github.com/fiatjaf/nostr/blob/master/nips/01.md
            pub key must be set to generate the id

            if you were doing we an existing event for some reason you'd need to change the pub_key
            as else the sig we give won't be as expected

        """
        self._get_id()

        pk = PrivateKey(bytes.fromhex(priv_key))

        id_bytes = (bytes(bytearray.fromhex(self._id)))
        sig = pk.sign_schnorr(message=id_bytes, aux_randomness=None)
        sig_hex = sig.hex()

        self._sig = sig_hex

    def event_data(self):
        return {
            'id': self._id,
            'pubkey': self._pub_key,
            'created_at': self._created_at,
            'kind': self._kind,
            'tags': self._tags.tags,
            'content': self._content,
            'sig': self._sig
        }
