# import flask-related packages
import re, datetime
from cmath import e
from fileinput import filename
from flask import Blueprint, g, flash, render_template, request, send_from_directory, abort, redirect, url_for
from webargs import fields, flaskparser
from flask_login import current_user

# import custom packages from the current repository
import libreforms
from app import display, log, tempfile_path, mailer, mongodb, conditional_decorator
from app.auth import login_required, session
from app.forms import parse_form_fields, checkGroup, reconcile_form_data_struct, progagate_forms, parse_options, compile_depends_on_data
import app.signing as signing
from app.models import Signing


# and finally, import other packages
import os
import pandas as pd



if display['allow_anonymous_form_submissions']:


    # this forks forms.py to provide slightly different functionality; yes, it allows you 
    # to create forms, like in the regular forms source, but it presumes that the end user
    # for these forms will not have login credentials; instead, you define the form with the
    # _allow_anonymous_access option set to True, and then the system allows those (in the future,
    # only those with the correct group/role) to share a signed URL via email. Therefore, there
    # is no home page for external forms; by their very nature, they are intended for single-form,
    # one-time use -- like a questionnaire, petition, or voting system.

    bp = Blueprint('external', __name__, url_prefix='/external')


    # this creates a route to request access
    @bp.route(f'/<form_name>', methods=['GET', 'POST'])
    # here we apply the login_required decorator if admins require users to be authenticated in order
    # to initiate external submissions, see 'require_auth_users_to_initiate_external_forms'.
    @conditional_decorator(login_required, display['require_auth_users_to_initiate_external_forms'])
    def request_external_forms(form_name):

        # first make sure this form existss
        try:
            forms = parse_options(form_name)
        except Exception as e:
            log.error(f'LIBREFORMS - {e}')
            abort(404)

        if not checkGroup(group='anonymous', struct=parse_options(form_name)):
            flash(f'Your system administrator has disabled this form for anonymous users.')
            return redirect(url_for('home'))


        # if the appropriate configurations are set, all us to proceed
        if request.method == 'POST' and display["allow_anonymous_form_submissions"] and forms['_allow_anonymous_access']:
            email = request.form['email']
            
            if not email:
                error = f'Please enter a valid email.' 
            elif email and not re.fullmatch(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', email):
                error = 'Invalid email.' 

            else:error=None

            if not error:
                try: 
                    key = signing.write_key_to_database(scope=f'external_{form_name.lower()}', expiration=48, active=1, email=email)
                    content = f"You may now submit form {form_name} at the following address: {display['domain']}/external/{form_name}/{key}. Please note this link will expire after 48 hours."
                    mailer.send_mail(subject=f'{display["site_name"]} {form_name} Submission Link', content=content, to_address=email, logfile=log)
                    flash("Form submission link successfully sent.")
                except Exception as e:
                    flash(e)
            else:
                flash(error)
                
        return render_template('app/external_request.html', 
            name=form_name,             
            display=display,
            suppress_navbar=True,
            user=current_user if display['require_auth_users_to_initiate_external_forms'] else None,
            type='external',
            )

    # this creates the route to each of the forms
    @bp.route(f'/<form_name>/<signature>', methods=['GET', 'POST'])
    def external_forms(form_name, signature):

        if not display['allow_anonymous_form_submissions']:
            flash('This feature has not been enabled by your system administrator.')
            return redirect(url_for('home'))

        if not checkGroup(group='anonymous', struct=parse_options(form_name)):
            flash(f'Your system administrator has disabled this form for anonymous users.')
            return redirect(url_for('home'))

        if not signing.verify_signatures(signature, redirect_to='home', 
                                            scope=f'external_{form_name.lower()}', abort_on_error=True):


            try:
                options = parse_options(form_name)
                forms = progagate_forms(form_name)

                if request.method == 'POST':
                    parsed_args = flaskparser.parser.parse(parse_form_fields(form_name), request, location="form")
                    mongodb.write_document_to_collection(parsed_args, form_name, reporter=" ".join((Signing.query.filter_by(signature=signature).first().email, signature))) 
                    flash(str(parsed_args))

                    # possibly exchange the section below for an actual email/name depending on the
                    # data we store in the signed_urls database.
                    log.info(f'{Signing.query.filter_by(signature=signature).first().email} {signature} - submitted \'{form_name}\' form.')

                    # print(Signing.query.filter_by(signature=signature).first().email)

                    signing.expire_key(signature)

                    return redirect(url_for('home'))

                return render_template('app/forms.html', 
                    context=forms,
                    name=form_name,             
                    options=options, 
                    display=display,
                    suppress_navbar=True,
                    signed_url=signature,
                    type='external',
                    depends_on=compile_depends_on_data(form_name, user_group='anonymous'),
                    filename = f'{form_name.lower().replace(" ","")}.csv' if options['_allow_csv_templates'] else False,
                    )

            except Exception as e:
                print(e)
                abort(404)
                return None

        else:
            abort(404)
            return None


    ####
    # leaving this, just in case the different base-route breaks the CSV download feature.
    ####
    @bp.route('/download/<path:filename>/<signature>')
    def download_file(filename, signature):

        if not display['allow_anonymous_form_submissions']:
            flash('This feature has not been enabled by your system administrator.')
            return redirect(url_for('home'))

        if not signing.verify_signatures(signature, redirect_to='auth.forgot_password', 
                                            scope="forgot_password"):


            # this is our first stab at building templates, without accounting for nesting or repetition
            df = pd.DataFrame (columns=[x for x in progagate_forms(filename.replace('.csv', '')).keys()])

            fp = os.path.join(tempfile_path, filename)
            df.to_csv(fp, index=False)

            return send_from_directory(tempfile_path,
                                    filename, as_attachment=True)
        else:
            abort(404)

