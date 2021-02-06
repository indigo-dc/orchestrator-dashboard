from flask import render_template, request
from app import app

@app.errorhandler(403)
def forbidden(error):
    return render_template('error_pages/403.html', message=error.description)

@app.errorhandler(404)
def page_not_found(error):
	app.logger.error('Page not found: %s', (request.path))
	return render_template('error_pages/404.html'), 404

@app.errorhandler(500)
def internal_server_error(error):
    app.logger.error('Server Error: %s', (error))
    return render_template('error_pages/500.html', support_email=app.config.get('SUPPORT_EMAIL')), 500
