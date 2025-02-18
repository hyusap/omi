import threading
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from database.redis_db import cache_user_geolocation, set_user_webhook_db, get_user_webhook_db
from database.users import *
from models.memory import Geolocation
from models.other import Person, CreatePerson
from utils.other import endpoints as auth
from utils.other.storage import delete_all_memory_recordings, get_user_person_speech_samples, \
    delete_user_person_speech_samples

router = APIRouter()


# TODO: url should be /v1/users
@router.delete('/v1/users/delete-account', tags=['v1'])
def delete_account(uid: str = Depends(auth.get_current_user_uid)):
    try:
        delete_user_data(uid)
        # delete user from firebase auth
        auth.delete_account(uid)
        return {'status': 'ok', 'message': 'Account deleted successfully'}
    except Exception as e:
        print('delete_account', str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch('/v1/users/geolocation', tags=['v1'])
def set_user_geolocation(geolocation: Geolocation, uid: str = Depends(auth.get_current_user_uid)):
    cache_user_geolocation(uid, geolocation.dict())
    return {'status': 'ok'}


class WebhookType(str, Enum):
    audio_bytes = 'audio_bytes'


@router.post('/v1/users/developer/webhook/{wtype}', tags=['v1'])
def set_user_webhook_endpoint(wtype: WebhookType, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    set_user_webhook_db(uid, wtype, data['url'])
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhook/{wtype}', tags=['v1'])
def get_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    return {'url': get_user_webhook_db(uid, wtype)}


# *************************************************
# ************* RECORDING PERMISSION **************
# *************************************************

@router.post('/v1/users/store-recording-permission', tags=['v1'])
def store_recording_permission(value: bool, uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, value)
    return {'status': 'ok'}


@router.get('/v1/users/store-recording-permission', tags=['v1'])
def get_store_recording_permission(uid: str = Depends(auth.get_current_user_uid)):
    return {'store_recording_permission': get_user_store_recording_permission(uid)}


@router.delete('/v1/users/store-recording-permission', tags=['v1'])
def delete_permission_and_recordings(uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, False)
    delete_all_memory_recordings(uid)
    return {'status': 'ok'}


# ****************************************
# ************* PEOPLE CRUD **************
# ****************************************

# TODO: consider adding person photo.
@router.post('/v1/users/people', tags=['v1'], response_model=Person)
def create_new_person(data: CreatePerson, uid: str = Depends(auth.get_current_user_uid)):
    data = {
        'id': str(uuid.uuid4()),
        'name': data.name,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
        'deleted': False,
    }
    result = create_person(uid, data)
    return result


@router.get('/v1/users/people/{person_id}', tags=['v1'], response_model=Person)
def get_single_person(
        person_id: str, include_speech_samples: bool = False, uid: str = Depends(auth.get_current_user_uid)
):
    person = get_person(uid, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if include_speech_samples:
        person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])
    return person


@router.get('/v1/users/people', tags=['v1'], response_model=List[Person])
def get_all_people(include_speech_samples: bool = True, uid: str = Depends(auth.get_current_user_uid)):
    print('get_all_people', include_speech_samples)
    people = get_people(uid)
    if include_speech_samples:
        def single(person):
            person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])

        threads = [threading.Thread(target=single, args=(person,)) for person in people]
        [t.start() for t in threads]
        [t.join() for t in threads]
    return people


@router.patch('/v1/users/people/{person_id}/name', tags=['v1'])
def update_person_name(
        person_id: str,
        value: str,  # = Field(min_length=2, max_length=40),
        uid: str = Depends(auth.get_current_user_uid),
):
    update_person(uid, person_id, value)
    return {'status': 'ok'}


@router.delete('/v1/users/people/{person_id}', tags=['v1'], status_code=204)
def delete_person_endpoint(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    delete_person(uid, person_id)
    delete_user_person_speech_samples(uid, person_id)
    return {'status': 'ok'}
