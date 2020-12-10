import os
import boto3
import json
import tempfile
from hamlet.backend.common.fsutils import Search
from .context_tree import (
    find_gen3_root_dir,
    find_gen3_dirs,
    upgrade_cmdb,
    cleanup_cmdb
)
from .environment import Environment
from .utils import deep_dict_update


def set_context(
    cwd=None,
    environment_obj=None
):
    e = environment_obj  # shortcut
    l = Environment()  # local env
    if e.GENERATION_CONTEXT_DEFINED:
        return
    e.GENERATION_CONTEXT_DEFINED = True
    l.GENERATION_CONTEXT_DEFINED_LOCAL = True
    if not e.GENERATION_TMPDIR:
        # *******************************************
        # * TODO: decide how to do temp dir cleanup *
        # *******************************************
        e.GENERATION_TMPDIR = tempfile.mkdtemp()
    e.GENERATION_DATA_DIR = find_gen3_root_dir(cwd)
    if not e.GENERATION_DATA_DIR:
        raise Exception("Can't locate the root of the directory tree.")
    if not e.GENERATION_NO_CMDB_CHECK:
        if not upgrade_cmdb(e.GENERATION_DATA_DIR, '', '', e.GENERATION_MAX_CMDB_UPGRADE_VERSION):
            raise Exception('CMDB upgrade failed.')
        if not cleanup_cmdb(e.GENERATION_DATA_DIR, '', '', e.GENERATION_MAX_CMDB_UPGRADE_VERSION):
            raise Exception('CMDB cleanup failed.')
    e.CACHE_DIR = os.path.join(e.GENERATION_DATA_DIR, 'cache')
    os.makedirs(e.CACHE_DIR, exist_ok=True)

    l.TEMPLATE_COMPOSITES = ('account', 'fragment')

    for composite in l.TEMPLATE_COMPOSITES:
        key = f'COMPOSITE_{composite.upper()}'
        e[key] = os.path.join(e.CACHE_DIR, f'{key.lower()}.ftl')

        if (
            not e.GENERATION_USE_CACHE and not
            e.GENERATION_USE_FRAGMENTS_CACHE or not
            Search.isfile(e.CACHE_DIR, 'composite_account.ftl')
        ):
            l[f'{composite.lower()}_array'] = []
            # ********************************************
            # * TODO: add legacy start fragments section *
            # ********************************************
    # Check if the current directory gives any clue to the context
    # Accommodate both pre cmdb v2.0.0 where segment/environment in the config tree
    # and post v2.0.0 where they are in the infrastructure tree
    l.solutions_ancestor_dir = Search.upwards(cwd, 'solutions')
    l.solutionsv2_ancestor_dir = Search.upwards(cwd, 'solutionsv2')
    if not l.solutions_ancestor_dir and not l.solutionsv2_ancestor_dir:
        l.infrastructure_dir = cwd.replace('settings', 'solutions')
        l.infrastructure_dir = l.infrastructure_dir.replace('operations', 'infrastructure')
        l.infrastructure_dir = l.infrastructure_dir.replace('config', 'infrastructure')
        if os.path.isdir(l.infrastructure_dir):
            cwd = l.infrastructure_dir
    if Search.isfile(cwd, 'segment.json'):
        e.LOCATION = e.LOCATION or 'segment'
        e.SEGMENT = Search.basename(cwd)
        if Search.isfile(cwd, 'environment.json', up=1):
            cwd = Search.parent(cwd, up=1)
        else:
            e.ENVIRONMENT = e.SEGMENT
            e.SEGMENT = 'default'
            cwd = os.path.join(Search.parent(cwd, up=3), 'config')
    if Search.isfile(cwd, 'environment.json'):
        e.LOCATION = e.LOCATION or 'environment'
        e.ENVIRONMENT = Search.basename(cwd)
        cwd = os.path.join(Search.parent(cwd, up=3), 'config')
    if Search.isfile(cwd, 'account.json'):
        # account directory
        # We check it before checking for a product as the account directory
        # also acts as a product directory for shared infrastructure
        # An account directory may also have no product information e.g.
        # in the case of production environments in dedicated accounts.
        e.LOCATION = e.LOCATION or 'account'
    if Search.isfile(cwd, 'product.json'):
        if e.LOCATION == 'account':
            e.LOCATION = 'account|product'
        else:
            e.LOCATION = e.LOCATION or 'product'
        e.PRODUCT = Search.basename(cwd)
        if e.PRODUCT == 'config':
            e.PRODUCT = Search.basename(cwd, up=1)
    if Search.isfile(cwd, 'integrator.json'):
        e.LOCATION = e.LOCATION or 'integrator'
        e.INTEGRATOR = Search.basename(cwd)
    if Search.isfile(cwd, 'root.json') or Search.isdir(cwd, 'config') and Search.isdir(cwd, 'infrastructure'):
        e.LOCATION = 'root'
    cwd = e.GENERATION_DATA_DIR
    if not e.ACCOUNT:
        e.ACCOUNT = Search.basename(e.GENERATION_DATA_DIR)
    # Analyse directory structure
    find_gen3_dirs(e, e.GENERATION_DATA_DIR)
    # Build the composite solution ( aka blueprint)
    e.GENERATION_INPUT_SOURCE = e.GENERATION_INPUT_SOURCE or 'composite'
    if e.GENERATION_INPUT_SOURCE == 'composite':
        l.blueprint_alternate_dirs = (
            e.SEGMENT_SOLUTIONS_DIR,
            e.ENVIRONMENT_SHARED_SOLUTIONS_DIR,
            e.SEGMENT_SHARED_SOLUTIONS_DIR,
            e.PRODUCT_SHARED_SOLUTIONS_DIR
        )
        e.COMPOSITE_BLUEPRINT = os.path.join(e.CACHE_DIR, 'composite_blueprint.json')
        if (
            not e.GENERATION_USE_CACHE
            and not e.GENERATION_USE_BLUEPRINT_CACHE
            or not os.path.isfile(e.COMPOSITE_BLUEPRINT)
        ):
            l.blueprint_array = []
            for blueprint_alternate_dir in l.blueprint_alternate_dirs:
                if not blueprint_alternate_dir or not os.path.isdir(blueprint_alternate_dir):
                    continue
                l.blueprint_array += Search.match_files(
                    os.path.join('**', 'segment*.json'),
                    os.path.join('**', 'environment*.json'),
                    os.path.join('**', 'solution*.json'),
                    os.path.join('**', 'domains*.json'),
                    os.path.join('**', 'ipaddressgroups*.json'),
                    os.path.join('**', 'countrygroups*.json'),
                    root=blueprint_alternate_dir
                )
            l.blueprint_array += Search.match_files(
                os.path.join('**', 'domains*.json'),
                os.path.join('**', 'ipaddressgroups*.json'),
                os.path.join('**', 'countrygroups*.json'),
                os.path.join('**', 'profiles*.json'),
                os.path.join('**', 'product*.json'),
                root=e.PRODUCT_DIR
            )
            l.blueprint_array += Search.match_files(
                os.path.join('**', 'domains*.json'),
                os.path.join('**', 'ipaddressgroups*.json'),
                os.path.join('**', 'countrygroups*.json'),
                os.path.join('**', 'account*.json'),
                root=e.ACCOUNT_DIR
            )
            l.blueprint_array += Search.match_files(
                os.path.join('**', 'domains*.json'),
                os.path.join('**', 'ipaddressgroups*.json'),
                os.path.join('**', 'countrygroups*.json'),
                os.path.join('**', 'profiles*.json'),
                os.path.join('**', 'tenant*.json'),
                root=e.TENANT_DIR
            )
            if not l.blueprint_array:
                blueprint = {}
                with open(e.COMPOSITE_BLUEPRINT, 'wt+') as f:
                    f.write('{}')
            else:
                #  merging blueprint components
                blueprint = {}
                for blueprint_component_json in l.blueprint_array:
                    with open(blueprint_component_json, 'rt') as f:
                        deep_dict_update(blueprint, json.load(f))
                with open(e.COMPOSITE_BLUEPRINT, 'wt+') as f:
                    json.dump(blueprint, f, indent=4, sort_keys=True)

            # Extract key settings from the composite solution
            tenant = blueprint.get('Tenant', {})
            account = blueprint.get('Account', {})
            product = blueprint.get('Product', {})
            segment = blueprint.get('Segment', {})
            e.TID = tenant.get('Id')
            e.TENANT = tenant.get('Name')
            e.AID = account.get('Id')
            e.PROVIDERID = account.get('ProviderId')
            e.ACCOUNT_REGION = account.get('Region')
            e.PID = product.get('Id')
            e.PRODUCT_REGION = product.get('Region')
            e.DEPLOYMENTUNIT_REGION = product.get(e.DEPLOYMENT_UNIT, {}).get('Region')
            e.SID = segment.get('Id')

            e.COMPONENT_REGION = e.DEPLOYMENTUNIT_REGION or e.PRODUCT_REGION
            e.REGION = e.REGION or e.COMPONENT_REGION
            # Perform a few consistency checks
            if not e.REGION:
                raise Exception("The region must be defined in the Product blueprint section.")

            l.BLUEPRINT_ACCOUNT = account.get('Name') or account.get('Id')
            l.BLUEPRINT_PRODUCT = product.get('Name') or product.get('Id')
            l.BLUEPRINT_SEGMENT = segment.get('Name') or segment.get('Id')
            if e.ACCOUNT and l.BLUEPRINT_ACCOUNT != 'Account' and e.ACCOUNT != l.BLUEPRINT_ACCOUNT:
                raise Exception(
                    f"Blueprint account of {l.BLUEPRINT_ACCOUNT} doesn't match expected value of {e.ACCOUNT}"
                )
            if e.PRODUCT and l.BLUEPRINT_PRODUCT != 'Product' and e.PRODUCT != l.BLUEPRINT_PRODUCT:
                raise Exception(
                    f"Blueprint product of {l.BLUEPRINT_PRODUCT} doesn't match expected value of ${e.PRODUCT}"
                )
            if e.SEGMENT and l.BLUEPRINT_SEGMENT != 'Segment' and e.SEGMENT != l.BLUEPRINT_SEGMENT:
                raise Exception(
                    f"Blueprint segment of {e.BLUEPRINT_SEGMENT} doesn't match expected value of {e.SEGMENT}"
                )
    # Set default AWS credentials if available (hook from Jenkins framework)
    l.CHECK_AWS_ACCESS_KEY_ID = (
        e.AWS_ACCESS_KEY_ID
        or e.ACCOUNT_TEMP_AWS_ACCESS_KEY_ID
        or e[e.ACCOUNT_AWS_ACCESS_KEY_ID_VAR]
    )
    if l.CHECK_AWS_ACCESS_KEY_ID:
        e.AWS_ACCESS_KEY_ID = l.CHECK_AWS_ACCESS_KEY_ID

    l.CHECK_AWS_SECRET_ACCESS_KEY = (
        e.AWS_SECRET_ACCESS_KEY
        or e.ACCOUNT_TEMP_AWS_SECRET_ACCESS_KEY
        or e[e.ACCOUNT_AWS_SECRET_ACCESS_KEY_VAR]
    )
    if l.CHECK_AWS_SECRET_ACCESS_KEY:
        e.AWS_SECRET_ACCESS_KEY = l.CHECK_AWS_SECRET_ACCESS_KEY

    l.CHECK_AWS_SESSION_TOKEN = e.AWS_SESSION_TOKEN or e.ACCOUNT_TEMP_AWS_SESSION_TOKEN
    if l.CHECK_AWS_SESSION_TOKEN:
        e.AWS_SESSION_TOKEN = l.CHECK_AWS_SESSION_TOKEN

    # Set the profile for IAM access if AWS credentials not in the environment
    if not e.AWS_ACCESS_KEY_ID or not e.AWS_SECRET_ACCESS_KEY:
        available_profiles = boto3.session.Session().available_profiles
        if e.ACCOUNT and e.ACCOUNT in available_profiles:
            e.AWS_DEFAULT_PROFILE = e.ACCOUNT
        if e.AID and e.AID in available_profiles:
            e.AWS_DEFAULT_PROFILE = e.AID
        if e.PROVIDERID and e.PROVIDERID in available_profiles:
            e.AWS_DEFAULT_PROFILE = e.PROVIDERID
